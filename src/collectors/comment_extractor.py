"""
Comment extractor - fetches and parses top comments from Reddit threads.

Adapted from last30days-skill reddit_enrich.py.
Comments often contain stronger user intent than the original post.
"""

import json
import time
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from ..utils.logger import get_logger
from config.settings import DEFAULT_TOP_COMMENTS_PER_POST

logger = get_logger(__name__)

USER_AGENT = "AilaWaitlistAgent/1.0 (travel app lead finder)"
MAX_RETRIES = 2
BASE_BACKOFF = 1.5


def _comment_to_dict(c_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a Reddit comment payload into the compact internal comment shape."""
    body = c_data.get("body", "").strip()

    if not body or body in ("[deleted]", "[removed]"):
        return None

    author = c_data.get("author", "[deleted]")
    if author in ("[deleted]", "[removed]"):
        return None

    return {
        "id": c_data.get("id"),
        "score": c_data.get("score", 0),
        "created_utc": c_data.get("created_utc"),
        "author": author,
        "body": body,
        "permalink": c_data.get("permalink", ""),
    }


def extract_reddit_path(url: str) -> Optional[str]:
    """Extract the path from a Reddit URL."""
    try:
        parsed = urlparse(url)
        if "reddit.com" not in parsed.netloc:
            return None
        return parsed.path
    except:
        return None


def fetch_thread_json(url: str, timeout: int = 10) -> Optional[Any]:
    """
    Fetch Reddit thread JSON data.

    Args:
        url: Reddit thread URL
        timeout: HTTP timeout in seconds

    Returns:
        Thread data or None on failure
    """
    path = extract_reddit_path(url)
    if not path:
        return None

    # Reddit thread JSON endpoint
    json_url = f"https://www.reddit.com{path}.json?raw_json=1"

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    req = urllib.request.Request(json_url, headers=headers)

    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)

        except urllib.error.HTTPError as e:
            if e.code == 429:
                delay = BASE_BACKOFF * (2 ** attempt)
                logger.warning(f"429 rate limited fetching thread, retry {attempt + 1}/{MAX_RETRIES}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(delay)
                    continue
                return None
            elif e.code in (404, 403):
                logger.warning(f"HTTP {e.code} fetching thread: {url}")
                return None
            else:
                logger.error(f"HTTP {e.code} error: {e.reason}")
                return None

        except Exception as e:
            logger.error(f"Error fetching thread JSON: {e}")
            return None

    return None


def parse_comments_from_thread(thread_data: Any) -> List[Dict[str, Any]]:
    """
    Parse comments from Reddit thread JSON.

    Args:
        thread_data: Raw Reddit JSON response

    Returns:
        List of comment dicts
    """
    comments = []

    if not isinstance(thread_data, list) or len(thread_data) < 2:
        return comments

    # Second element is comments listing
    comments_listing = thread_data[1]
    if not isinstance(comments_listing, dict):
        return comments

    children = comments_listing.get("data", {}).get("children", [])

    for child in children:
        if child.get("kind") != "t1":  # t1 = comment
            continue

        c_data = child.get("data", {})
        comment = _comment_to_dict(c_data)
        if comment:
            comments.append(comment)

        # Lightweight one-level nested reply scan; do not expand "more" nodes.
        replies = c_data.get("replies")
        if isinstance(replies, dict):
            reply_children = replies.get("data", {}).get("children", [])
            for reply_child in reply_children:
                if reply_child.get("kind") != "t1":
                    continue
                reply = _comment_to_dict(reply_child.get("data", {}))
                if reply:
                    comments.append(reply)

    return comments


def get_top_comments(comments: List[Dict[str, Any]], limit: int = DEFAULT_TOP_COMMENTS_PER_POST) -> List[Dict[str, Any]]:
    """
    Get top comments sorted by score.

    Args:
        comments: List of comment dicts
        limit: Maximum number to return

    Returns:
        Top comments sorted by score
    """
    # Sort by score descending
    sorted_comments = sorted(comments, key=lambda c: c.get("score", 0), reverse=True)
    return sorted_comments[:limit]


def extract_comments_for_post(post: Dict[str, Any], top_n: int = DEFAULT_TOP_COMMENTS_PER_POST) -> List[Dict[str, Any]]:
    """
    Extract top comments for a Reddit post.

    Args:
        post: Reddit post dict with 'url' field
        top_n: Number of top comments to extract

    Returns:
        List of top comment dicts
    """
    url = post.get("url", "")
    if not url:
        return []

    logger.debug(f"Extracting comments from: {url}")

    thread_data = fetch_thread_json(url)
    if not thread_data:
        return []

    all_comments = parse_comments_from_thread(thread_data)
    top_comments = get_top_comments(all_comments, limit=top_n)

    logger.debug(f"  Extracted {len(top_comments)} comments")

    return top_comments


def enrich_posts_with_comments(
    posts: List[Dict[str, Any]],
    top_n_comments: int = DEFAULT_TOP_COMMENTS_PER_POST,
    max_posts_to_enrich: int = 30,
) -> List[Dict[str, Any]]:
    """
    Enrich posts with their top comments.

    Args:
        posts: List of Reddit posts
        top_n_comments: Number of top comments per post
        max_posts_to_enrich: Maximum posts to process (to avoid rate limits)

    Returns:
        Posts with 'top_comments' field added
    """
    logger.info(f"Enriching {min(len(posts), max_posts_to_enrich)} posts with comments...")

    selected_posts = posts[:max_posts_to_enrich]
    remaining_posts = posts[max_posts_to_enrich:]
    enriched_by_url = {}

    for i, post in enumerate(selected_posts):
        if i > 0 and i % 10 == 0:
            logger.info(f"  Progress: {i}/{min(len(posts), max_posts_to_enrich)}")
            time.sleep(1)  # Brief pause to be respectful

        try:
            top_comments = extract_comments_for_post(post, top_n=top_n_comments)
            post["top_comments"] = top_comments
            enriched_by_url[post.get("url")] = post
        except Exception as e:
            logger.error(f"Error enriching post {post.get('url')}: {e}")
            post["top_comments"] = []
            enriched_by_url[post.get("url")] = post
            continue

    # Preserve original post order for downstream scoring/ranking.
    enriched = []
    for post in posts:
        url = post.get("url")
        if url in enriched_by_url:
            enriched.append(enriched_by_url[url])
            continue
        post["top_comments"] = []
        enriched.append(post)

    logger.info(f"Comment enrichment complete")

    return enriched


def extract_comment_leads(
    posts: List[Dict[str, Any]],
    min_comment_score: float = 15.0,  # Lowered to capture realistic comment leads
) -> List[Dict[str, Any]]:
    """
    Extract high-intent comments as separate leads.

    Identifies commenters who express shared pain points or actively seek solutions.

    Args:
        posts: List of posts with 'top_comments' field
        min_comment_score: Minimum lead score for comment to become a lead

    Returns:
        List of comment-based lead dicts
    """
    # Import here to avoid circular dependency
    from ..scoring.lead_scorer import score_comment_as_lead
    from ..scoring.lead_scorer import calculate_age_hours, calculate_recency_score

    logger.info(f"Extracting comment-based leads from {len(posts)} posts...")

    comment_leads = []
    seen_comment_urls = set()
    total_comments_analyzed = 0
    skipped_deleted = 0
    skipped_low_score = 0
    skipped_duplicate = 0
    all_scored_comments = []  # For debug analysis

    for post in posts:
        top_comments = post.get("top_comments", [])
        if not top_comments:
            continue

        post_title = post.get("title", "")
        post_url = post.get("url", "")
        subreddit = post.get("subreddit", "")
        post_text = post.get("selftext", "")
        post_context = f"{post_title} {post_text}"

        for comment in top_comments:
            comment_text = comment.get("body", "")
            author = comment.get("author", "")
            comment_url = f"https://www.reddit.com{comment.get('permalink', '')}"

            # Skip deleted/removed comments
            if not comment_text or author in ("[deleted]", "[removed]", "AutoModerator"):
                skipped_deleted += 1
                continue

            if not comment.get("permalink") or comment_url in seen_comment_urls:
                skipped_duplicate += 1
                continue
            seen_comment_urls.add(comment_url)

            total_comments_analyzed += 1

            # Score comment for lead quality
            comment_score, matched_indicators = score_comment_as_lead(comment_text, post_context)
            comment_age_hours = calculate_age_hours(comment)
            comment_recency_score = calculate_recency_score(comment)

            # Store for debug analysis
            all_scored_comments.append({
                "score": comment_score,
                "text": comment_text[:100],
                "author": author,
                "indicators": matched_indicators,
                "subreddit": subreddit,
            })

            # Only keep high-intent comments
            if comment_score < min_comment_score:
                skipped_low_score += 1
                continue

            # Build comment lead dict
            comment_lead = {
                "url": comment_url,
                "title": post_title,
                "subreddit": subreddit,
                "source": "reddit",
                "source_id": comment.get("id"),
                "author": post.get("author", ""),  # Original post author
                "reddit_username": author,  # Comment author (the actual lead)
                "selftext": comment_text,
                "comment_text": comment_text,
                "parent_post_url": post_url,
                "score": comment.get("score", 0),
                "num_comments": 0,  # Comments don't have replies in this context
                "created_utc": comment.get("created_utc", 0),
                "lead_score": comment_score,
                "lead_type": "comment",
                "score_breakdown": {
                    "total_score": comment_score,
                    "comment_indicators": matched_indicators,
                    "age_hours": round(comment_age_hours, 2) if comment_age_hours is not None else None,
                    "recency_score": round(comment_recency_score, 2),
                    "score_reason": f"Comment lead: {', '.join(matched_indicators[:3])}",
                },
            }

            comment_leads.append(comment_lead)

    # Debug logging
    logger.info(f"Comment extraction statistics:")
    logger.info(f"  - Total comments analyzed: {total_comments_analyzed}")
    logger.info(f"  - Skipped (deleted/removed): {skipped_deleted}")
    logger.info(f"  - Skipped (low score < {min_comment_score}): {skipped_low_score}")
    logger.info(f"  - Skipped (duplicate URL): {skipped_duplicate}")
    logger.info(f"  - Extracted as leads: {len(comment_leads)}")

    # Show top 10 highest-scoring comments for debugging
    if all_scored_comments:
        top_10 = sorted(all_scored_comments, key=lambda x: x["score"], reverse=True)[:10]
        logger.info(f"\nTop 10 highest-scoring comments:")
        for i, c in enumerate(top_10, 1):
            logger.info(f"  {i}. Score: {c['score']:.1f} | r/{c['subreddit']} | u/{c['author']}")
            logger.info(f"     Text: {c['text']}")
            logger.info(f"     Indicators: {c['indicators']}")

    logger.info(f"\nFound {len(comment_leads)} high-intent comment leads")

    return comment_leads

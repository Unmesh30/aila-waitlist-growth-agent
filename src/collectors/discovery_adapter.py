"""
Discovery adapter - adapted from last30days-skill reddit_public.py.

Uses Reddit's public JSON endpoints to fetch recent subreddit listings and,
optionally, search for supplemental content.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from ..utils.logger import get_logger
from config.settings import REDDIT_USER_AGENT, REDDIT_TIMEOUT

logger = get_logger(__name__)

MAX_RETRIES = 3
BASE_BACKOFF = 2.0  # seconds


def url_encode(text: str) -> str:
    """URL-encode a query string."""
    return urllib.parse.quote_plus(text)


def build_headers() -> Dict[str, str]:
    """Build request headers for Reddit public JSON endpoints."""
    return {
        "User-Agent": REDDIT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://www.reddit.com/",
        "Origin": "https://www.reddit.com",
    }


def fetch_json(url: str, timeout: int = REDDIT_TIMEOUT) -> Optional[Dict[str, Any]]:
    """
    Fetch JSON from a URL with retry on 429 and error handling.

    Returns parsed JSON dict, or None on unrecoverable failure.
    """
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers=build_headers())
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "json" not in content_type and "text/html" in content_type:
                    logger.warning(f"Anti-bot HTML response (Content-Type: {content_type})")
                    return None

                body = resp.read().decode("utf-8")
                return json.loads(body)

        except urllib.error.HTTPError as e:
            if e.code == 429:
                delay = BASE_BACKOFF * (2 ** attempt)
                retry_after = None
                if hasattr(e, "headers"):
                    retry_after = e.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        pass
                logger.warning(f"429 rate limited, retry {attempt + 1}/{MAX_RETRIES} after {delay:.1f}s")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(delay)
                    continue
                logger.error("429 retries exhausted")
                return None
            elif e.code == 404:
                logger.warning(f"404 not found: {url}")
                return None
            elif e.code == 403:
                logger.warning(f"403 forbidden: {url}")
                return None
            else:
                logger.error(f"HTTP {e.code}: {e.reason}")
                return None

        except (urllib.error.URLError, OSError, TimeoutError) as e:
            logger.error(f"Network error: {e}")
            return None

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return None

    return None


def parse_reddit_posts(data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse Reddit listing JSON into normalized post dicts."""
    if not data:
        return []

    children = data.get("data", {}).get("children", [])
    posts = []

    for child in children:
        if child.get("kind") != "t3":  # t3 = submission
            continue

        post = child.get("data", {})
        permalink = str(post.get("permalink", "")).strip()
        if not permalink or "/comments/" not in permalink:
            continue

        score = int(post.get("score", 0) or 0)
        num_comments = int(post.get("num_comments", 0) or 0)
        selftext = str(post.get("selftext", ""))
        author = str(post.get("author", "[deleted]"))
        created_utc = post.get("created_utc")

        # Parse date
        date_str = None
        if created_utc:
            try:
                dt = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
                date_str = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError, OSError):
                pass

        posts.append({
            "title": str(post.get("title", "")).strip(),
            "url": f"https://www.reddit.com{permalink}",
            "source": "reddit",
            "source_id": str(post.get("id", "")).strip() or None,
            "score": score,
            "num_comments": num_comments,
            "subreddit": str(post.get("subreddit", "")).strip(),
            "created_utc": float(created_utc) if created_utc else None,
            "author": author if author not in ("[deleted]", "[removed]") else "[deleted]",
            "selftext": selftext,
            "date": date_str,
            "upvote_ratio": post.get("upvote_ratio"),
        })

    return posts


def search_reddit(
    query: str,
    limit: int = 50,
    subreddit: Optional[str] = None,
    time_filter: str = "month",
    sort: str = "relevance",
    timeout: int = 15,
) -> List[Dict[str, Any]]:
    """
    Search Reddit via public JSON endpoints.

    Args:
        query: Search query string
        limit: Maximum number of results
        subreddit: Optional subreddit name (without r/) for scoped search
        time_filter: Time filter (hour, day, week, month, year, all)
        sort: Sort order (relevance, hot, top, new, comments)
        timeout: HTTP timeout in seconds

    Returns:
        List of normalized post dicts. Empty list on any failure.
    """
    encoded_query = url_encode(query)

    if subreddit:
        sub = subreddit.lstrip("r/").strip()
        candidate_urls = [
            (
                f"https://old.reddit.com/r/{sub}/search.json"
                f"?q={encoded_query}&restrict_sr=on&sort={sort}&t={time_filter}&limit={limit}&raw_json=1"
            ),
            (
                f"https://www.reddit.com/r/{sub}/search.json"
                f"?q={encoded_query}&restrict_sr=on&sort={sort}&t={time_filter}&limit={limit}&raw_json=1"
            ),
        ]
        logger.info(f"Searching r/{sub} for: {query}")
    else:
        candidate_urls = [
            (
                f"https://old.reddit.com/search.json"
                f"?q={encoded_query}&sort={sort}&t={time_filter}&limit={limit}&raw_json=1"
            ),
            (
                f"https://www.reddit.com/search.json"
                f"?q={encoded_query}&sort={sort}&t={time_filter}&limit={limit}&raw_json=1"
            ),
        ]
        logger.info(f"Searching Reddit for: {query}")

    for url in candidate_urls:
        data = fetch_json(url, timeout=timeout)
        posts = parse_reddit_posts(data)
        if posts:
            logger.info(f"Found {len(posts)} posts")
            return posts

    logger.info("Found 0 posts")
    return []


def fetch_subreddit_recent(
    subreddit: str,
    limit: int = 25,
    listing: str = "new",
    timeout: int = REDDIT_TIMEOUT,
) -> List[Dict[str, Any]]:
    """
    Fetch recent posts directly from a subreddit listing endpoint.

    Args:
        subreddit: Subreddit name (without r/)
        limit: Maximum number of posts to fetch
        listing: Listing type, typically "new" or "hot"
        timeout: HTTP timeout in seconds

    Returns:
        List of normalized post dicts
    """
    sub = subreddit.lstrip("r/").strip()
    url = (
        f"https://www.reddit.com/r/{sub}/{listing}.json"
        f"?limit={limit}&raw_json=1"
    )

    logger.info(f"Fetching r/{sub}/{listing} listing")
    data = fetch_json(url, timeout=timeout)
    posts = parse_reddit_posts(data)
    logger.info(f"Found {len(posts)} recent posts in r/{sub}")
    return posts

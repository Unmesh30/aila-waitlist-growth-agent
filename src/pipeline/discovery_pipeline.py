"""
Discovery pipeline - orchestrates Reddit collection, enrichment, scoring, and ranking.

Steps:
1. Collect posts from Reddit
2. Extract top comments
3. Score leads (rules-based)
4. Rank and filter using non-LLM scoring only
"""

from typing import List, Dict, Any

from ..collectors.reddit_recent_collector import collect_recent_discussions
from ..collectors.comment_extractor import enrich_posts_with_comments, extract_comment_leads
from ..collectors.x_collector import collect_recent_tweets
from ..scoring.lead_scorer import score_all_posts
from ..scoring.ranker import rank_leads, print_ranking_summary
from ..storage.repository import LeadRepository
from ..utils.logger import get_logger
from config.settings import TARGET_CANDIDATE_POOL, TARGET_FINAL_LEADS
from config.x_settings import X_MAX_COLLECTION_LIMIT

logger = get_logger(__name__)


def _post_enrichment_priority(post: Dict[str, Any]) -> tuple:
    """Sort key for choosing which Reddit posts should get comment enrichment first."""
    score_breakdown = post.get("score_breakdown", {}) or {}
    age_hours = score_breakdown.get("age_hours")
    try:
        age_value = float(age_hours) if age_hours is not None else float("inf")
    except (TypeError, ValueError):
        age_value = float("inf")

    return (
        age_value,
        -float(post.get("lead_score", 0) or 0),
        -int(post.get("num_comments", 0) or 0),
        -int(post.get("score", 0) or 0),
    )


def _prioritize_posts_for_comment_enrichment(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prioritize recent, engaged, relevant Reddit posts for comment enrichment."""
    return sorted(posts, key=_post_enrichment_priority)


def _filter_existing_leads(
    leads: List[Dict[str, Any]],
    repository: LeadRepository,
    label: str,
) -> List[Dict[str, Any]]:
    """
    Remove leads that already exist in the database based on lead URL.

    Args:
        leads: Candidate leads
        repository: Repository for existence checks
        label: Log label for this dedup pass

    Returns:
        Only leads whose URLs are not already present in the database
    """
    raw_count = len(leads)
    urls = [lead.get("url") for lead in leads if lead.get("url")]
    existing_urls = repository.get_existing_lead_urls(urls)

    filtered_leads = [lead for lead in leads if lead.get("url") not in existing_urls]
    removed_count = raw_count - len(filtered_leads)

    logger.info(
        "%s: %d raw candidates, %d removed as existing DB leads, %d truly new remain",
        label,
        raw_count,
        removed_count,
        len(filtered_leads),
    )

    return filtered_leads


def run_discovery_pipeline(
    enrich_comments: bool = True,
    max_posts_to_enrich: int = 30,
    extract_comment_based_leads: bool = True,
) -> List[Dict[str, Any]]:
    """
    Run the complete discovery pipeline.

    Args:
        enrich_comments: Whether to fetch comments
        max_posts_to_enrich: Maximum posts to enrich with comments
        extract_comment_based_leads: Whether to extract high-intent comments as separate leads

    Returns:
        List of final ranked leads (both posts and comments)
    """
    logger.info("=" * 60)
    logger.info("STARTING DISCOVERY PIPELINE")
    logger.info("=" * 60)

    # Step 1: Collect source candidates
    logger.info("\n[1/5] Collecting Reddit posts...")
    reddit_posts = collect_recent_discussions(target_candidate_pool=TARGET_CANDIDATE_POOL)
    for post in reddit_posts:
        post.setdefault("source", "reddit")

    logger.info("\n[1b/5] Collecting X tweets...")
    x_tweets = collect_recent_tweets(max_tweets=X_MAX_COLLECTION_LIMIT)

    posts = reddit_posts + x_tweets

    if not posts:
        logger.warning("No source candidates collected. Pipeline stopped.")
        return []

    logger.info(
        "Collected %d raw candidates total (%d Reddit posts, %d X tweets)",
        len(posts),
        len(reddit_posts),
        len(x_tweets),
    )

    repository = LeadRepository()
    try:
        posts = _filter_existing_leads(posts, repository, "Post DB dedup")

        if not posts:
            logger.warning("All collected posts already exist in the database. Pipeline stopped.")
            return []

        reddit_posts = [post for post in posts if post.get("source", "reddit") == "reddit"]
        x_posts = [post for post in posts if post.get("source") == "x"]

        # Step 2: Score posts before comment enrichment so the enrichment subset can
        # prioritize recent, engaged, relevant Reddit posts.
        logger.info("\n[2/5] Pre-scoring posts for comment enrichment priority...")
        prescored_reddit_posts = score_all_posts(reddit_posts)
        reddit_posts_for_enrichment = _prioritize_posts_for_comment_enrichment(prescored_reddit_posts)

        # Step 3: Enrich with comments
        if enrich_comments:
            logger.info(f"\n[3/5] Enriching top {max_posts_to_enrich} prioritized Reddit posts with comments...")
            enriched_prioritized_posts = enrich_posts_with_comments(
                reddit_posts_for_enrichment,
                max_posts_to_enrich=max_posts_to_enrich,
            )
            enriched_by_url = {post.get("url"): post for post in enriched_prioritized_posts}
            reddit_posts = [enriched_by_url.get(post.get("url"), post) for post in prescored_reddit_posts]
        else:
            logger.info("\n[3/5] Skipping comment enrichment")
            for post in reddit_posts:
                post["top_comments"] = []
        for post in x_posts:
            post["top_comments"] = []

        posts = reddit_posts + x_posts

        # Step 4: Score all posts with enriched comments included
        logger.info("\n[4/5] Scoring posts...")
        scored_posts = score_all_posts(posts)

        # Add lead_type to post leads
        for post in scored_posts:
            if "lead_type" not in post:
                post["lead_type"] = "tweet" if post.get("source") == "x" else "post"
            if "reddit_username" not in post:
                post["reddit_username"] = post.get("author")

        # Step 5: Extract comment-based leads
        comment_leads = []
        if extract_comment_based_leads and enrich_comments:
            logger.info("\n[5/5] Extracting high-intent comment leads...")
            reddit_scored_posts = [post for post in scored_posts if post.get("source", "reddit") == "reddit"]
            comment_leads = extract_comment_leads(reddit_scored_posts, min_comment_score=15.0)

        # Combine post leads and comment leads, then filter out anything already stored.
        all_leads = scored_posts + comment_leads
        logger.info(
            f"Total leads before DB dedup: {len(scored_posts)} posts + {len(comment_leads)} comments = {len(all_leads)}"
        )
        all_leads = _filter_existing_leads(all_leads, repository, "Combined lead DB dedup")

        if not all_leads:
            logger.warning("No new leads remain after DB dedup. Pipeline stopped.")
            return []

        # Step 6: Rank and filter
        logger.info("\n[6/6] Ranking and filtering all leads...")

        # Debug: log input to ranking
        input_posts = sum(1 for lead in all_leads if lead.get("lead_type") == "post")
        input_comments = sum(1 for lead in all_leads if lead.get("lead_type") == "comment")
        input_tweets = sum(1 for lead in all_leads if lead.get("lead_type") == "tweet")
        logger.info(
            f"Input to ranking: {len(all_leads)} total ({input_posts} posts, {input_comments} comments, {input_tweets} tweets)"
        )

        top_leads = rank_leads(all_leads)

        # Debug: log output from ranking
        logger.info(
            f"\nAfter ranking: {len(top_leads)} leads kept after rules-based filtering (target: {TARGET_FINAL_LEADS})"
        )

        # Count by type
        post_leads_count = sum(1 for lead in top_leads if lead.get("lead_type") == "post")
        comment_leads_count = sum(1 for lead in top_leads if lead.get("lead_type") == "comment")
        tweet_leads_count = sum(1 for lead in top_leads if lead.get("lead_type") == "tweet")

        # Debug: show detailed breakdown
        logger.info(f"Final lead breakdown:")
        logger.info(f"  - Post leads: {post_leads_count}")
        logger.info(f"  - Comment leads: {comment_leads_count}")
        logger.info(f"  - Tweet leads: {tweet_leads_count}")

        # Debug: show comment lead details if any
        if comment_leads_count > 0:
            comment_lead_list = [lead for lead in top_leads if lead.get("lead_type") == "comment"]
            logger.info(f"\nComment leads in final set:")
            for i, lead in enumerate(comment_lead_list[:5], 1):
                logger.info(f"  {i}. [{lead.get('lead_score', 0):.1f}] u/{lead.get('reddit_username', 'unknown')}")
                logger.info(f"     r/{lead.get('subreddit', '')} - {lead.get('comment_text', '')[:80]}")
        else:
            logger.warning(f"\n⚠️  No comment leads in final set! Checking why...")
            # Check if comment leads had too low scores
            comment_scores = [lead.get('lead_score', 0) for lead in all_leads if lead.get('lead_type') == 'comment']
            if comment_scores:
                logger.warning(f"   Comment score range: {min(comment_scores):.1f} - {max(comment_scores):.1f}")
                logger.warning(f"   MIN_LEAD_SCORE threshold: 5")
                logger.warning(
                    f"   Top lead scores: {sorted([lead.get('lead_score', 0) for lead in all_leads], reverse=True)[:10]}"
                )

        # Print summary
        print_ranking_summary(all_leads, top_leads)

        logger.info("\n" + "=" * 60)
        logger.info(f"DISCOVERY COMPLETE: {len(top_leads)} qualified leads from non-LLM ranking")
        logger.info(f"  - 📝 Post leads: {post_leads_count}")
        logger.info(f"  - 💬 Comment leads: {comment_leads_count}")
        logger.info(f"  - 𝕏 Tweet leads: {tweet_leads_count}")
        logger.info("=" * 60)

        return top_leads
    finally:
        repository.close()

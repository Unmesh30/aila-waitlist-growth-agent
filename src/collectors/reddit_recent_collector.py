"""
Reddit recent collector - discovers travel-related discussions.

Searches across multiple travel subreddits and queries to find
recent discussions that match Aila's user pain points.
"""

from typing import List, Dict, Any

from .discovery_adapter import fetch_subreddit_recent, search_reddit
from ..utils.logger import get_logger
from config.sources import TRAVEL_SUBREDDITS, TRAVEL_PAIN_QUERIES, REDDIT_TIME_FILTER, REDDIT_SORT_ORDER
from config.settings import (
    REDDIT_SEARCH_LIMIT,
    REDDIT_SUBREDDIT_LIMIT,
    TARGET_CANDIDATE_POOL,
    MAX_COLLECTION_PASSES,
)

logger = get_logger(__name__)


def collect_from_subreddits(
    queries: List[str],
    subreddits: List[str],
    limit_per_search: int = 10,
) -> List[Dict[str, Any]]:
    """
    Collect posts from specific subreddits using multiple queries.

    Args:
        queries: List of search queries
        subreddits: List of subreddit names
        limit_per_search: Limit per query-subreddit combination

    Returns:
        Combined list of posts
    """
    all_posts = []
    total_searches = len(queries) * len(subreddits)

    logger.info(f"Starting subreddit collection: {len(queries)} queries × {len(subreddits)} subreddits = {total_searches} searches")

    for subreddit in subreddits:
        for query in queries:
            try:
                posts = search_reddit(
                    query=query,
                    subreddit=subreddit,
                    limit=limit_per_search,
                    time_filter=REDDIT_TIME_FILTER,
                    sort=REDDIT_SORT_ORDER,
                )

                # Keep collector working if subreddit search endpoints fail.
                if not posts:
                    posts = fetch_subreddit_recent(
                        subreddit=subreddit,
                        limit=max(3, limit_per_search),
                        listing="new",
                    )

                all_posts.extend(posts)
                logger.debug(f"  r/{subreddit} + '{query}': {len(posts)} posts")
            except Exception as e:
                logger.error(f"Error searching r/{subreddit} for '{query}': {e}")
                continue

    logger.info(f"Collected {len(all_posts)} posts from subreddit searches")
    return all_posts


def collect_global_search(
    queries: List[str],
    limit_per_query: int = 25,
) -> List[Dict[str, Any]]:
    """
    Collect posts from global Reddit search.

    Args:
        queries: List of search queries
        limit_per_query: Limit per query

    Returns:
        Combined list of posts
    """
    all_posts = []

    logger.info(f"Starting global Reddit search: {len(queries)} queries")

    for query in queries:
        try:
            posts = search_reddit(
                query=query,
                limit=limit_per_query,
                time_filter=REDDIT_TIME_FILTER,
                sort=REDDIT_SORT_ORDER,
            )
            all_posts.extend(posts)
            logger.debug(f"  '{query}': {len(posts)} posts")
        except Exception as e:
            logger.error(f"Error in global search for '{query}': {e}")
            continue

    logger.info(f"Collected {len(all_posts)} posts from global search")
    return all_posts


def _dedupe_posts(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate posts by Reddit URL while preserving order."""
    seen_urls = set()
    unique_posts = []

    for post in posts:
        url = post.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_posts.append(post)

    return unique_posts


def collect_recent_discussions(target_candidate_pool: int = TARGET_CANDIDATE_POOL) -> List[Dict[str, Any]]:
    """
    Main collection function - discovers recent travel discussions.

    Strategy:
    1. Search high-priority travel subreddits with focused queries
    2. Supplement with global Reddit search
    3. If still too small for the overnight queue, expand carefully
    4. Deduplicate and return combined results

    Returns:
        List of unique posts
    """
    logger.info("=" * 60)
    logger.info("Starting Reddit collection")
    logger.info("=" * 60)

    all_posts: List[Dict[str, Any]] = []
    passes = [
        {
            "subreddits": TRAVEL_SUBREDDITS[:6],
            "queries": TRAVEL_PAIN_QUERIES[:5],
            "limit_per_search": 8,
            "global_queries": TRAVEL_PAIN_QUERIES,
            "global_limit": 15,
        },
        {
            "subreddits": TRAVEL_SUBREDDITS[:12],
            "queries": TRAVEL_PAIN_QUERIES[:10],
            "limit_per_search": 10,
            "global_queries": TRAVEL_PAIN_QUERIES[:14],
            "global_limit": 20,
        },
        {
            "subreddits": TRAVEL_SUBREDDITS,
            "queries": TRAVEL_PAIN_QUERIES,
            "limit_per_search": 12,
            "global_queries": TRAVEL_PAIN_QUERIES,
            "global_limit": 25,
        },
    ]

    for pass_index, pass_config in enumerate(passes[:MAX_COLLECTION_PASSES], 1):
        logger.info(f"Collection pass {pass_index}/{min(len(passes), MAX_COLLECTION_PASSES)}")

        subreddit_posts = collect_from_subreddits(
            queries=pass_config["queries"],
            subreddits=pass_config["subreddits"],
            limit_per_search=pass_config["limit_per_search"],
        )
        all_posts.extend(subreddit_posts)

        global_posts = collect_global_search(
            queries=pass_config["global_queries"],
            limit_per_query=pass_config["global_limit"],
        )
        all_posts.extend(global_posts)

        unique_posts = _dedupe_posts(all_posts)
        logger.info(
            f"After pass {pass_index}: {len(all_posts)} collected → {len(unique_posts)} unique candidates"
        )
        if len(unique_posts) >= target_candidate_pool:
            all_posts = unique_posts
            break

        all_posts = unique_posts

    unique_posts = _dedupe_posts(all_posts)
    logger.info(f"Deduplication: {len(all_posts)} → {len(unique_posts)} unique posts")
    logger.info("=" * 60)

    return unique_posts

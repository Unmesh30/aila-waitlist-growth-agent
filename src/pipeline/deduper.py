"""
Deduper - removes duplicate posts and comments.

Simple URL-based deduplication for now.
"""

from typing import List, Dict, Any

from ..utils.logger import get_logger

logger = get_logger(__name__)


def deduplicate_by_url(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate posts based on URL.

    Args:
        posts: List of post dicts

    Returns:
        Deduplicated list
    """
    seen_urls = set()
    unique = []

    for post in posts:
        url = post.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(post)

    if len(posts) > len(unique):
        logger.info(f"Deduplication: {len(posts)} → {len(unique)} posts")

    return unique


def deduplicate_comments(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate comments based on body text.

    Args:
        comments: List of comment dicts

    Returns:
        Deduplicated list
    """
    seen_bodies = set()
    unique = []

    for comment in comments:
        body = comment.get("body", "").strip()
        if body and body not in seen_bodies:
            seen_bodies.add(body)
            unique.append(comment)

    return unique

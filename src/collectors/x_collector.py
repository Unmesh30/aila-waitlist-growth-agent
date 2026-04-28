"""
X collector - lightweight recent tweet discovery via HTTP.

Uses the optional X recent search API when a bearer token is available.
Returns tweets normalized into the lead structure used by the pipeline.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

from ..utils.logger import get_logger
from config.x_settings import (
    ENABLE_X_COLLECTION,
    X_BEARER_TOKEN,
    X_ENGAGEMENT_THRESHOLD,
    X_MAX_COLLECTION_LIMIT,
    X_MAX_RESULTS_PER_QUERY,
    X_RECENCY_WINDOW_HOURS,
    X_SEARCH_QUERIES,
)

logger = get_logger(__name__)

X_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

QUESTION_MARKERS = ["?", "how", "what", "where", "anyone", "recommend", "tips"]
FRUSTRATION_MARKERS = ["stressful", "stressed", "overwhelmed", "messy", "chaos", "frustrating", "confused"]
TOOL_INTENT_MARKERS = ["app", "tool", "recommendation", "recommend", "workflow", "organize", "itinerary"]


def _build_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {X_BEARER_TOKEN}",
        "Accept": "application/json",
        "User-Agent": "AilaWaitlistAgent/1.0",
    }


def _parse_timestamp(created_at: str | None) -> float | None:
    if not created_at:
        return None
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        return None


def _has_high_intent(text: str) -> bool:
    lower = text.lower()
    return (
        any(marker in lower for marker in QUESTION_MARKERS) or
        any(marker in lower for marker in FRUSTRATION_MARKERS) or
        any(marker in lower for marker in TOOL_INTENT_MARKERS)
    )


def _normalize_tweet(tweet: Dict[str, Any], users: Dict[str, Dict[str, Any]]) -> Dict[str, Any] | None:
    metrics = tweet.get("public_metrics", {}) or {}
    author_id = tweet.get("author_id")
    user = users.get(author_id, {}) if author_id else {}
    username = user.get("username")
    tweet_id = tweet.get("id")
    text = (tweet.get("text") or "").strip()

    if not tweet_id or not username or not text:
        return None

    like_count = int(metrics.get("like_count", 0) or 0)
    reply_count = int(metrics.get("reply_count", 0) or 0)
    engagement_score = like_count + reply_count

    return {
        "title": text[:100],
        "selftext": text,
        "url": f"https://x.com/{username}/status/{tweet_id}",
        "source": "x",
        "source_id": tweet_id,
        "subreddit": "x",
        "author": username,
        "reddit_username": username,
        "lead_type": "tweet",
        "score": like_count,
        "num_comments": reply_count,
        "created_utc": _parse_timestamp(tweet.get("created_at")),
        "upvote_ratio": None,
        "top_comments": [],
        "date": None,
        "engagement_score": engagement_score,
        "like_count": like_count,
        "reply_count": reply_count,
    }


def _search_query(query: str, limit: int) -> List[Dict[str, Any]]:
    if not ENABLE_X_COLLECTION:
        logger.info("X collection disabled by config")
        return []
    if not X_BEARER_TOKEN:
        logger.warning("X bearer token not configured; skipping X collection")
        return []

    start_time = (datetime.now(timezone.utc) - timedelta(hours=X_RECENCY_WINDOW_HOURS)).isoformat().replace("+00:00", "Z")
    params = {
        "query": f'"{query}" lang:en -is:retweet -is:reply',
        "max_results": min(limit, 100),
        "start_time": start_time,
        "tweet.fields": "created_at,public_metrics,author_id",
        "expansions": "author_id",
        "user.fields": "username",
    }

    try:
        response = requests.get(
            X_SEARCH_URL,
            headers=_build_headers(),
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("X search failed for query '%s': %s", query, exc)
        return []

    users = {
        user.get("id"): user
        for user in payload.get("includes", {}).get("users", [])
        if user.get("id")
    }

    tweets = []
    for tweet in payload.get("data", []) or []:
        normalized = _normalize_tweet(tweet, users)
        if not normalized:
            continue
        if normalized["engagement_score"] < X_ENGAGEMENT_THRESHOLD and not _has_high_intent(normalized["selftext"]):
            continue
        tweets.append(normalized)

    return tweets


def collect_recent_tweets(max_tweets: int = X_MAX_COLLECTION_LIMIT) -> List[Dict[str, Any]]:
    """
    Collect recent high-intent travel tweets and normalize them into lead dicts.
    """
    logger.info("Collecting recent X tweets...")
    collected: List[Dict[str, Any]] = []
    seen_urls = set()
    per_query_limit = max(5, min(X_MAX_RESULTS_PER_QUERY, max_tweets))

    for query in X_SEARCH_QUERIES:
        if len(collected) >= max_tweets:
            break

        results = _search_query(query, per_query_limit)
        logger.info("X query '%s' returned %d tweets", query, len(results))

        for tweet in results:
            url = tweet.get("url")
            if not url or url in seen_urls:
                continue
            if not _has_high_intent(tweet.get("selftext", "")) and tweet.get("engagement_score", 0) < X_ENGAGEMENT_THRESHOLD:
                continue
            seen_urls.add(url)
            collected.append(tweet)
            if len(collected) >= max_tweets:
                break

    logger.info("Collected %d unique X tweets", len(collected))
    return collected

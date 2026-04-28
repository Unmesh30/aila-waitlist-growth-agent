"""
Ranker - sorts and filters scored leads.

Provides ranking, filtering, and summary statistics.
"""

from typing import List, Dict, Any, Tuple
from collections import Counter

from ..utils.logger import get_logger
from config.settings import (
    MIN_LEAD_SCORE,
    MIN_LEADS_TO_KEEP,
    MAX_LEADS_TO_KEEP,
    TARGET_FINAL_LEADS,
    MAX_OLDER_EXCEPTIONAL_LEADS,
)
from config.sources import get_promo_mode, promotion_flags_for_mode

logger = get_logger(__name__)


def _get_age_hours(post: Dict[str, Any]) -> float | None:
    breakdown = post.get("score_breakdown", {})
    age_hours = breakdown.get("age_hours")
    try:
        return float(age_hours) if age_hours is not None else None
    except (TypeError, ValueError):
        return None


def _is_exceptionally_active(post: Dict[str, Any]) -> bool:
    """Allow slightly older threads only if they're still clearly alive."""
    return (
        post.get("num_comments", 0) >= 20 or
        post.get("score", 0) >= 40 or
        post.get("lead_score", 0) >= 65
    )


def _recency_bucket(post: Dict[str, Any]) -> int:
    """
    Lower bucket is better:
    0 = <=48h
    1 = <=3d
    2 = <=7d
    3 = older but exceptionally active and within 14d
    4 = ineligible for overnight queue
    """
    age_hours = _get_age_hours(post)
    if age_hours is None:
        return 4
    if age_hours <= 48:
        return 0
    if age_hours <= 72:
        return 1
    if age_hours <= 24 * 7:
        return 2
    if age_hours <= 24 * 14 and _is_exceptionally_active(post):
        return 3
    return 4


def _rank_sort_key(post: Dict[str, Any]) -> tuple:
    age_hours = _get_age_hours(post)
    recency_value = age_hours if age_hours is not None else float("inf")
    promo_mode = post.get("promo_mode") or get_promo_mode(
        post.get("subreddit", ""),
        source=post.get("source", "reddit"),
    )
    promo_priority = 0 if promo_mode == "link_allowed" else 1
    return (
        _recency_bucket(post),
        promo_priority,
        -post.get("lead_score", 0),
        -post.get("num_comments", 0),
        -post.get("score", 0),
        recency_value,
    )

def _apply_promo_policy(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Annotate a lead with promotion policy flags used by ranking/drafting/dashboard."""
    promo_mode = get_promo_mode(
        lead.get("subreddit", ""),
        source=lead.get("source", "reddit"),
    )
    flags = promotion_flags_for_mode(promo_mode)
    lead["promo_mode"] = flags["promo_mode"]
    lead["subreddit_policy_mode"] = flags["promo_mode"]
    lead["link_allowed"] = flags["link_allowed"]
    lead["mention_allowed"] = flags["mention_allowed"]
    lead["actionable_for_promotion"] = flags["actionable_for_promotion"]
    return lead

def rank_leads(scored_posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Rank leads by score with dynamic top-N selection.

    Strategy:
    1. Sort all leads by score (descending)
    2. Keep leads with score >= MIN_LEAD_SCORE (soft threshold)
    3. If < MIN_LEADS_TO_KEEP qualified, keep top MIN_LEADS_TO_KEEP anyway
    4. Cap at MAX_LEADS_TO_KEEP

    This ensures we always get 20-50 leads even when scores are low.

    Args:
        scored_posts: Leads (posts + comments) with lead_score field

    Returns:
        Filtered and sorted list of top leads
    """
    if not scored_posts:
        logger.warning("No leads to rank")
        return []

    policy_annotated = [_apply_promo_policy(post) for post in scored_posts]
    actionable_posts = [post for post in policy_annotated if post.get("actionable_for_promotion")]
    excluded_count = len(policy_annotated) - len(actionable_posts)
    if excluded_count:
        logger.info(
            "Promotion policy filter: excluded %d disallowed/unclear leads before final queue",
            excluded_count,
        )

    eligible_recent = []
    older_exceptional = []
    ineligible = []

    for post in actionable_posts:
        bucket = _recency_bucket(post)
        if bucket in (0, 1, 2):
            eligible_recent.append(post)
        elif bucket == 3:
            older_exceptional.append(post)
        else:
            ineligible.append(post)

    eligible_recent = sorted(eligible_recent, key=_rank_sort_key)
    older_exceptional = sorted(older_exceptional, key=_rank_sort_key)[:MAX_OLDER_EXCEPTIONAL_LEADS]
    eligible_posts = eligible_recent + older_exceptional

    # Filter by soft threshold
    above_threshold = [p for p in eligible_posts if p.get("lead_score", 0) >= MIN_LEAD_SCORE]

    # Dynamic selection logic
    if len(above_threshold) >= TARGET_FINAL_LEADS:
        top_leads = above_threshold[:TARGET_FINAL_LEADS]
        logger.info(
            f"Dynamic ranking: {len(scored_posts)} leads → {len(actionable_posts)} promo-actionable "
            f"→ {len(eligible_posts)} recency-eligible "
            f"({len(older_exceptional)} older exceptions) → kept top {len(top_leads)}"
        )
    elif len(eligible_posts) >= TARGET_FINAL_LEADS:
        top_leads = eligible_posts[:TARGET_FINAL_LEADS]
        logger.warning(
            f"Only {len(above_threshold)} eligible leads above threshold ({MIN_LEAD_SCORE}); "
            f"using full eligible set ordering to reach {len(top_leads)}"
        )
    elif len(eligible_posts) >= MIN_LEADS_TO_KEEP:
        top_leads = eligible_posts
        logger.warning(
            f"Only {len(eligible_posts)} leads satisfied overnight recency/activity rules; keeping all of them"
        )
    else:
        top_leads = eligible_posts[:MIN_LEADS_TO_KEEP]
        logger.warning(
            f"Dynamic ranking: only {len(eligible_posts)} leads passed overnight recency/activity rules; "
            f"keeping {len(top_leads)}"
        )
        if top_leads:
            logger.warning(
                f"Score range of kept leads: {top_leads[-1].get('lead_score', 0):.1f} - {top_leads[0].get('lead_score', 0):.1f}"
            )

    return top_leads


def get_score_distribution(scored_posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate score distribution statistics.

    Args:
        scored_posts: Posts with lead_score field

    Returns:
        Distribution statistics
    """
    if not scored_posts:
        return {
            "count": 0,
            "min": 0,
            "max": 0,
            "avg": 0,
            "buckets": {},
        }

    scores = [p.get("lead_score", 0) for p in scored_posts]

    # Score buckets
    buckets = {
        "0-20": 0,
        "20-40": 0,
        "40-60": 0,
        "60-80": 0,
        "80-100": 0,
    }

    for score in scores:
        if score < 20:
            buckets["0-20"] += 1
        elif score < 40:
            buckets["20-40"] += 1
        elif score < 60:
            buckets["40-60"] += 1
        elif score < 80:
            buckets["60-80"] += 1
        else:
            buckets["80-100"] += 1

    return {
        "count": len(scores),
        "min": round(min(scores), 2),
        "max": round(max(scores), 2),
        "avg": round(sum(scores) / len(scores), 2),
        "buckets": buckets,
    }


def get_top_keywords(scored_posts: List[Dict[str, Any]], top_n: int = 10) -> List[Tuple[str, int]]:
    """
    Get most common matched keywords across all posts.

    Args:
        scored_posts: Posts with score_breakdown field
        top_n: Number of top keywords to return

    Returns:
        List of (keyword, count) tuples
    """
    all_keywords = []

    for post in scored_posts:
        breakdown = post.get("score_breakdown", {})
        keywords = breakdown.get("matched_keywords", [])
        all_keywords.extend(keywords)

    counter = Counter(all_keywords)
    return counter.most_common(top_n)


def print_ranking_summary(scored_posts: List[Dict[str, Any]], top_leads: List[Dict[str, Any]]):
    """
    Print ranking summary with statistics.

    Args:
        scored_posts: All scored leads (posts + comments)
        top_leads: Filtered top leads
    """
    logger.info("=" * 60)
    logger.info("RANKING SUMMARY")
    logger.info("=" * 60)

    # Distribution
    dist = get_score_distribution(scored_posts)
    logger.info(f"Total leads scored: {dist['count']}")
    logger.info(f"Score range: {dist['min']} - {dist['max']} (avg: {dist['avg']})")
    logger.info(f"Score distribution:")
    for bucket, count in dist['buckets'].items():
        logger.info(f"  {bucket}: {count} leads")

    # Top keywords
    top_keywords = get_top_keywords(scored_posts, top_n=10)
    logger.info(f"\nTop matched keywords:")
    for keyword, count in top_keywords:
        logger.info(f"  '{keyword}': {count} leads")

    # Top leads preview
    logger.info(f"\nTop {min(10, len(top_leads))} leads:")
    for i, lead in enumerate(top_leads[:10], 1):
        score = lead.get("lead_score", 0)
        title = lead.get("title", "")[:60]
        subreddit = lead.get("subreddit", "")
        reason = lead.get("score_breakdown", {}).get("score_reason", "")[:60]
        lead_type = lead.get("lead_type", "post")
        source = lead.get("source", "reddit")

        # Show type badge
        if lead_type == "comment":
            type_badge = "💬"
        elif lead_type == "tweet":
            type_badge = "𝕏"
        else:
            type_badge = "📝"

        location = f"r/{subreddit}" if source == "reddit" else "x"
        logger.info(f"  {i}. {type_badge} [{score:.1f}] {location}: {title}")
        logger.info(f"      → {reason}")

    logger.info("=" * 60)

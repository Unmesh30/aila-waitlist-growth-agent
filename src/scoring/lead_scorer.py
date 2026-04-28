"""
Lead scorer - calculates quality scores for potential waitlist leads.

Uses a practical weighted scoring system based on:
- Pain point mentions
- Request indicators (asking for help)
- Engagement signals
- Recency
- Post quality
"""

import re
from typing import Dict, Any, List, Tuple
from datetime import datetime, timezone

from ..utils.logger import get_logger
from config.scoring import (
    PAIN_POINT_KEYWORDS,
    REQUEST_INDICATORS,
    QUALITY_INDICATORS,
    SCORING_WEIGHTS,
    RECENCY_DECAY,
    TRAVEL_CONTEXT_KEYWORDS,
    COMMENT_LEAD_INDICATORS,
)
from config.sources import HIGH_QUALITY_TRAVEL_SUBREDDITS, BLOCKED_SUBREDDITS

logger = get_logger(__name__)


def calculate_age_hours(post: Dict[str, Any]) -> float | None:
    """Return lead age in hours if a valid timestamp exists."""
    created_utc = post.get("created_utc")
    if not created_utc:
        return None

    try:
        post_date = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
        now = datetime.now(timezone.utc)
        return max(0.0, (now - post_date).total_seconds() / 3600.0)
    except Exception:
        return None


def calculate_pain_point_score(text: str) -> Tuple[float, List[str]]:
    """
    Calculate pain point score based on keyword matches.

    Args:
        text: Text to analyze (title + selftext + comments)

    Returns:
        Tuple of (score, matched_keywords)
    """
    text_lower = text.lower()
    total_score = 0
    matched = []

    for keyword, weight in PAIN_POINT_KEYWORDS.items():
        if keyword in text_lower:
            total_score += weight
            matched.append(keyword)

    # Normalize to 0-100
    max_possible = 50  # Rough upper bound
    normalized = min(100, (total_score / max_possible) * 100)

    return normalized, matched


def calculate_request_score(text: str) -> Tuple[float, List[str]]:
    """
    Calculate request score - is the user asking for help?

    Args:
        text: Text to analyze

    Returns:
        Tuple of (score, matched_indicators)
    """
    text_lower = text.lower()
    matches = []

    for indicator in REQUEST_INDICATORS:
        if indicator in text_lower:
            matches.append(indicator)

    # More matches = stronger request signal
    if len(matches) >= 3:
        score = 100
    elif len(matches) == 2:
        score = 70
    elif len(matches) == 1:
        score = 40
    else:
        score = 0

    return score, matches


def calculate_engagement_score(post: Dict[str, Any]) -> float:
    """
    Calculate engagement score based on Reddit metrics.

    Args:
        post: Post dict with score and num_comments

    Returns:
        Normalized engagement score (0-100)
    """
    score = post.get("score", 0)
    num_comments = post.get("num_comments", 0)
    source = post.get("source", "reddit")

    # Log scale for engagement
    import math
    if source == "x":
        score_component = min(100, math.log1p(score) * 16)
        comments_component = min(100, math.log1p(num_comments) * 22)
    else:
        score_component = min(100, math.log1p(score) * 10)
        comments_component = min(100, math.log1p(num_comments) * 15)

    # Weighted combination
    engagement = (score_component * 0.45) + (comments_component * 0.55) if source == "x" else (score_component * 0.6) + (comments_component * 0.4)

    return min(100, engagement)


def calculate_recency_score(post: Dict[str, Any]) -> float:
    """
    Calculate recency score based on post age.

    Args:
        post: Post dict with created_utc or date

    Returns:
        Recency score (0-100)
    """
    age_hours = calculate_age_hours(post)
    if age_hours is None:
        return 50  # Unknown date = middle score

    age_days = age_hours / 24.0

    if age_hours <= 48:
        return 100
    if age_hours <= 72:
        return 92
    if age_days <= 7:
        return 78
    if age_days <= 14:
        return 50
    if age_days <= 30:
        return 30
    return 15


def calculate_quality_score(post: Dict[str, Any]) -> float:
    """
    Calculate quality score based on post specificity and detail.

    Args:
        post: Post dict with title and selftext

    Returns:
        Quality score (0-100)
    """
    title = post.get("title", "")
    selftext = post.get("selftext", "")
    combined = f"{title} {selftext}"
    source = post.get("source", "reddit")

    score = 0

    # Length check
    min_length = 35 if source == "x" else QUALITY_INDICATORS["min_length"]
    if len(combined) >= min_length:
        score += 30

    # Has a question mark?
    if "?" in combined:
        score += QUALITY_INDICATORS["has_question"] * 10

    # Multiple sentences suggests detail
    sentences = len([s for s in combined.split(".") if len(s.strip()) > 10])
    if sentences >= 3:
        score += QUALITY_INDICATORS["has_details"] * 10

    # Has numbers/specifics?
    if re.search(r'\d+', combined):
        score += 10

    return min(100, score)


def calculate_x_signal_score(post: Dict[str, Any], text: str) -> Tuple[float, List[str]]:
    """
    Extra scoring for X tweets using question, engagement, and tool-intent signals.
    """
    if post.get("source") != "x":
        return 0.0, []

    lower = text.lower()
    total = 0.0
    reasons: List[str] = []

    if "?" in text or any(token in lower for token in ("how do", "anyone", "what's", "recommend", "tips")):
        total += 25
        reasons.append("question_tweet")

    if any(token in lower for token in ("stress", "overwhelmed", "frustrating", "mess", "chaos")):
        total += 18
        reasons.append("frustration")

    if any(token in lower for token in ("app", "tool", "recommendation", "workflow", "organize", "itinerary")):
        total += 22
        reasons.append("tool_intent")

    if post.get("num_comments", 0) >= 2:
        total += 15
        reasons.append("has_replies")

    if post.get("score", 0) >= 3:
        total += 10
        reasons.append("has_likes")

    if len(text.split()) < 6:
        total -= 15
        reasons.append("too_generic")

    return max(0.0, min(100.0, total)), reasons


def has_travel_context(text: str) -> Tuple[bool, List[str]]:
    """
    Check if text has travel-related context.

    Posts without travel context are penalized or excluded.

    Args:
        text: Text to analyze

    Returns:
        Tuple of (has_travel_context, matched_travel_keywords)
    """
    text_lower = text.lower()
    matched = []

    for keyword in TRAVEL_CONTEXT_KEYWORDS:
        if keyword in text_lower:
            matched.append(keyword)

    has_context = len(matched) > 0
    return has_context, matched


def calculate_subreddit_modifier(subreddit: str, source: str = "reddit") -> Tuple[float, str]:
    """
    Calculate subreddit quality boost/penalty.

    Args:
        subreddit: Subreddit name

    Returns:
        Tuple of (modifier, reason)
    """
    if source == "x":
        return 0, ""

    subreddit_lower = subreddit.lower()

    # Block irrelevant subreddits completely
    if subreddit_lower in [s.lower() for s in BLOCKED_SUBREDDITS]:
        return -50, f"Blocked subreddit: {subreddit}"

    # Boost high-quality travel subreddits
    if subreddit_lower in [s.lower() for s in HIGH_QUALITY_TRAVEL_SUBREDDITS]:
        return 20, f"High-quality travel subreddit: {subreddit}"

    # No modifier for other subreddits
    return 0, ""


def calculate_lead_score(post: Dict[str, Any], comments: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Calculate comprehensive lead quality score.

    Args:
        post: Reddit post dict
        comments: Optional list of comment dicts

    Returns:
        Score breakdown dict
    """
    # Combine text from post and top comments
    title = post.get("title", "")
    selftext = post.get("selftext", "")
    combined_text = f"{title} {selftext}"
    source = post.get("source", "reddit")

    # Include top comments in text analysis
    if comments:
        comment_text = " ".join([c.get("body", "") for c in comments[:5]])
        combined_text += " " + comment_text

    # Calculate component scores
    pain_score, pain_keywords = calculate_pain_point_score(combined_text)
    request_score, request_indicators = calculate_request_score(combined_text)
    engagement_score = calculate_engagement_score(post)
    recency_score = calculate_recency_score(post)
    quality_score = calculate_quality_score(post)
    x_signal_score, x_signal_reasons = calculate_x_signal_score(post, combined_text)
    age_hours = calculate_age_hours(post)

    # Check travel context (CRITICAL)
    has_context, travel_keywords = has_travel_context(combined_text)

    # Calculate subreddit modifier
    subreddit = post.get("subreddit", "")
    subreddit_modifier, subreddit_reason = calculate_subreddit_modifier(subreddit, source=source)

    # Weighted total
    total_score = (
        pain_score * SCORING_WEIGHTS["pain_points"] +
        request_score * SCORING_WEIGHTS["request"] +
        engagement_score * SCORING_WEIGHTS["engagement"] +
        recency_score * SCORING_WEIGHTS["recency"] +
        quality_score * SCORING_WEIGHTS["quality"]
    )

    if source == "x":
        total_score += x_signal_score * 0.35

    # Apply travel context penalty (STRONG)
    # Posts without travel context get massive penalty
    if not has_context:
        total_score *= 0.3  # 70% penalty
        travel_penalty_reason = "No travel context"
    else:
        travel_penalty_reason = f"Travel: {', '.join(travel_keywords[:3])}"

    # Apply subreddit modifier
    total_score += subreddit_modifier

    # Ensure score is within 0-100 range
    total_score = max(0, min(100, total_score))

    # Build explanation
    reasons = []

    # Travel context first (critical)
    reasons.append(travel_penalty_reason)

    if subreddit_reason:
        reasons.append(subreddit_reason)

    if pain_keywords:
        reasons.append(f"Pain: {', '.join(pain_keywords[:3])}")
    if request_indicators:
        reasons.append(f"Asks: {', '.join(request_indicators[:2])}")
    if x_signal_reasons:
        reasons.append(f"X: {', '.join(x_signal_reasons[:3])}")
    if engagement_score > 50:
        reasons.append(f"{post.get('score', 0)}↑ {post.get('num_comments', 0)}💬")

    return {
        "total_score": round(total_score, 2),
        "pain_point_score": round(pain_score, 2),
        "request_score": round(request_score, 2),
        "engagement_score": round(engagement_score, 2),
        "recency_score": round(recency_score, 2),
        "quality_score": round(quality_score, 2),
        "x_signal_score": round(x_signal_score, 2),
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "subreddit_modifier": round(subreddit_modifier, 2),
        "has_travel_context": has_context,
        "travel_keywords": travel_keywords[:5],
        "matched_keywords": pain_keywords[:5],
        "request_indicators": request_indicators[:3],
        "score_reason": " | ".join(reasons) if reasons else "Low relevance",
    }


def score_comment_as_lead(comment_text: str, post_context: str = "") -> Tuple[float, List[str]]:
    """
    Score a comment for lead quality.

    Comments that express shared pain or seek solutions are potential leads.

    Args:
        comment_text: The comment body
        post_context: Optional post title/text for context

    Returns:
        Tuple of (score, matched_indicators)
    """
    text_lower = comment_text.lower()
    combined = f"{comment_text} {post_context}".lower()

    total_score = 0
    matched = []

    # Check comment-specific lead indicators
    for indicator, weight in COMMENT_LEAD_INDICATORS.items():
        if indicator in text_lower:
            total_score += weight
            matched.append(indicator)

    # Also check for general pain points
    for keyword, weight in PAIN_POINT_KEYWORDS.items():
        if keyword in text_lower:
            total_score += weight * 0.7  # Slightly lower weight for comments
            matched.append(keyword)

    # Check travel context
    has_travel_context = any(kw in combined for kw in TRAVEL_CONTEXT_KEYWORDS)

    # Reduced penalty if no travel context
    # Many comments don't repeat travel keywords but are clearly in travel posts
    if not has_travel_context:
        total_score *= 0.7

    # Normalize to 0-100 with adjusted max
    max_possible = 80
    normalized = min(100, (total_score / max_possible) * 100)

    return normalized, matched[:8]


def score_all_posts(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Score all posts and add score fields.

    Args:
        posts: List of posts with optional 'top_comments' field

    Returns:
        Posts with added score fields
    """
    logger.info(f"Scoring {len(posts)} posts...")

    scored = []

    for post in posts:
        comments = post.get("top_comments", [])
        score_data = calculate_lead_score(post, comments)

        # Add score fields to post
        post["lead_score"] = score_data["total_score"]
        post["score_breakdown"] = score_data

        scored.append(post)

    logger.info("Scoring complete")

    return scored

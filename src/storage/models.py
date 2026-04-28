"""
Data models for leads.

Defines the structure of lead records.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum


class LeadStatus(Enum):
    """Lead status enum."""
    NEW = "new"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"


class Lead:
    """Lead model representing a potential waitlist candidate (post or comment)."""

    def __init__(
        self,
        url: str,
        title: str,
        subreddit: str,
        source: str,
        author: str,
        selftext: str,
        score: int,
        num_comments: int,
        created_utc: float,
        lead_score: float,
        score_breakdown: Dict[str, Any],
        source_id: Optional[str] = None,
        lead_type: str = "post",  # "post" or "comment"
        reddit_username: Optional[str] = None,  # Username to reply to
        comment_text: Optional[str] = None,  # Comment body if comment lead
        parent_post_url: Optional[str] = None,  # Original post URL if comment lead
        reply: Optional[str] = None,
        reply_sources: Optional[list[Dict[str, Any]]] = None,
        subreddit_policy_mode: Optional[str] = None,
        promo_mode: Optional[str] = None,
        link_allowed: bool = False,
        mention_allowed: bool = False,
        actionable_for_promotion: bool = False,
        promotion_allowed: bool = False,
        link_included: bool = False,
        aila_mentioned: bool = False,
        status: LeadStatus = LeadStatus.NEW,
        discovered_at: Optional[datetime] = None,
        post_id: Optional[int] = None,
    ):
        self.post_id = post_id
        self.url = url
        self.title = title
        self.subreddit = subreddit
        self.source = source
        self.author = author
        self.selftext = selftext
        self.score = score
        self.num_comments = num_comments
        self.created_utc = created_utc
        self.lead_score = lead_score
        self.score_breakdown = score_breakdown
        self.source_id = source_id
        self.lead_type = lead_type
        self.reddit_username = reddit_username or author
        self.comment_text = comment_text
        self.parent_post_url = parent_post_url
        self.reply = reply
        self.reply_sources = reply_sources or []
        self.promo_mode = promo_mode or subreddit_policy_mode or "disallowed_or_unclear"
        self.subreddit_policy_mode = subreddit_policy_mode or self.promo_mode
        self.link_allowed = link_allowed
        self.mention_allowed = mention_allowed
        self.actionable_for_promotion = actionable_for_promotion
        self.promotion_allowed = promotion_allowed
        self.link_included = link_included
        self.aila_mentioned = aila_mentioned
        self.status = status
        self.discovered_at = discovered_at or datetime.now()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Lead':
        """
        Create Lead from dictionary.

        Args:
            data: Lead data dict

        Returns:
            Lead instance
        """
        reply = data.get("reply")
        reply_sources = data.get("reply_sources", [])

        return cls(
            url=data["url"],
            title=data["title"],
            subreddit=data["subreddit"],
            source=data.get("source", "reddit"),
            author=data["author"],
            selftext=data.get("selftext", ""),
            score=data.get("score", 0),
            num_comments=data.get("num_comments", 0),
            created_utc=data.get("created_utc", 0),
            lead_score=data.get("lead_score", 0),
            score_breakdown=data.get("score_breakdown", {}),
            source_id=data.get("source_id"),
            lead_type=data.get("lead_type", "post"),
            reddit_username=data.get("reddit_username"),
            comment_text=data.get("comment_text"),
            parent_post_url=data.get("parent_post_url"),
            reply=reply,
            reply_sources=reply_sources,
            subreddit_policy_mode=data.get("subreddit_policy_mode"),
            promo_mode=data.get("promo_mode"),
            link_allowed=data.get("link_allowed", False),
            mention_allowed=data.get("mention_allowed", False),
            actionable_for_promotion=data.get("actionable_for_promotion", False),
            promotion_allowed=data.get("promotion_allowed", False),
            link_included=data.get("link_included", False),
            aila_mentioned=data.get("aila_mentioned", False),
            status=LeadStatus.NEW,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert Lead to dictionary for database storage.

        Returns:
            Dict representation
        """
        return {
            "post_id": self.post_id,
            "url": self.url,
            "title": self.title,
            "subreddit": self.subreddit,
            "source": self.source,
            "author": self.author,
            "selftext": self.selftext,
            "score": self.score,
            "num_comments": self.num_comments,
            "created_utc": self.created_utc,
            "lead_score": self.lead_score,
            "score_breakdown": self.score_breakdown,
            "source_id": self.source_id,
            "lead_type": self.lead_type,
            "reddit_username": self.reddit_username,
            "comment_text": self.comment_text,
            "parent_post_url": self.parent_post_url,
            "reply": self.reply,
            "reply_sources": self.reply_sources,
            "subreddit_policy_mode": self.subreddit_policy_mode,
            "promo_mode": self.promo_mode,
            "link_allowed": self.link_allowed,
            "mention_allowed": self.mention_allowed,
            "actionable_for_promotion": self.actionable_for_promotion,
            "promotion_allowed": self.promotion_allowed,
            "link_included": self.link_included,
            "aila_mentioned": self.aila_mentioned,
            "status": self.status.value,
            "discovered_at": self.discovered_at.isoformat(),
        }

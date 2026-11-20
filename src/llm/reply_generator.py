"""
Reply generator - generates single high-quality reply using Ollama.

Creates one natural, founder-tone reply focused on waitlist growth.
"""

import re
import zlib
import time
from collections import defaultdict
from typing import Dict, Any, List, Optional

from .ollama_client import OllamaClient
from .prompts import (
    SYSTEM_PROMPT,
    build_reply_prompt,
    build_x_reply_prompt,
    get_comments_summary,
)
from .source_grounder import (
    detect_grounding_need,
    gather_sources_for_lead,
    format_sources_for_prompt,
)
from ..utils.logger import get_logger
from config.settings import (
    AILA_NAME,
    AILA_WAITLIST_URL,
    ENABLE_REPLY_GROUNDING,
    MAX_LINKED_REPLIES_PER_RUN,
    MAX_PROMOTIONAL_MENTIONS_PER_RUN,
    MAX_PROMO_REPLIES_PER_SUBREDDIT_PER_RUN,
    OLLAMA_FALLBACK_MODEL,
)
from config.sources import get_promo_mode, promotion_flags_for_mode
from config.x_settings import (
    X_DELAY_BETWEEN_GENERATIONS,
    X_MAX_REPLIES_GENERATED,
    X_MAX_REPLIES_PER_USER,
)

logger = get_logger(__name__)


class ReplyGenerator:
    """Generates single high-quality reply for leads using local Ollama."""

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        """
        Initialize reply generator.

        Args:
            ollama_client: Optional OllamaClient instance
        """
        self.client = ollama_client or OllamaClient()
        self.promotional_mentions_used = 0
        self.linked_replies_used = 0
        self.promo_replies_by_subreddit = defaultdict(int)
        self.x_replies_generated = 0
        self.x_replies_by_user = defaultdict(int)

    def _get_policy_mode(self, subreddit: str, source: str = "reddit") -> str:
        return get_promo_mode(subreddit, source=source)

    def _is_strong_fit(self, lead: Dict[str, Any]) -> bool:
        lead_score = float(lead.get("lead_score", 0) or 0)
        score_breakdown = lead.get("score_breakdown", {}) or {}
        request_score = float(score_breakdown.get("request_score", 0) or 0)
        pain_score = float(score_breakdown.get("pain_point_score", 0) or 0)
        return lead_score >= 70 or (request_score >= 70 and pain_score >= 60)

    def _choose_style_variant(self, lead: Dict[str, Any]) -> str:
        variants = [
            "direct_help",
            "empathy_first",
            "tactical_first",
            "thread_broadening",
        ]
        stable_key = lead.get("url") or lead.get("title") or ""
        # zlib.crc32 gives the same number in every run; Python's hash() of a string changes per process.
        return variants[zlib.crc32(stable_key.encode("utf-8")) % len(variants)]

    def _plan_outreach(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        subreddit = lead.get("subreddit", "")
        source = lead.get("source", "reddit")
        if source == "x":
            return self._plan_x_outreach(lead)

        policy_mode = self._get_policy_mode(subreddit, source=source)
        flags = promotion_flags_for_mode(policy_mode)
        allow_aila_mention = False
        allow_link = False

        if not flags["actionable_for_promotion"]:
            allow_aila_mention = False
            allow_link = False
        elif policy_mode == "link_allowed":
            allow_aila_mention = True
            allow_link = True
        elif policy_mode == "mention_only":
            allow_aila_mention = True

        return {
            "policy_mode": policy_mode,
            "allow_aila_mention": allow_aila_mention,
            "allow_link": allow_link,
            "style_variant": self._choose_style_variant(lead),
        }

    def _plan_x_outreach(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "policy_mode": "link_allowed",
            "allow_aila_mention": True,
            "allow_link": True,
            "style_variant": self._choose_style_variant(lead),
        }

    def _sanitize_reply(
        self,
        reply: str,
        allow_aila_mention: bool,
        allow_link: bool,
        source_urls: Optional[List[str]] = None,
    ) -> str:
        """Enforce the outreach rules on the model's text, whatever the model wrote.

        - Links: keep the waitlist link only where links are allowed, plus links to the official
          sources the reply was given. Every other link goes (models invent them). A markdown link
          keeps its words; a sentence whose only content is a disallowed link is dropped.
        - @handles are removed (models invent accounts).
        - Where promotion isn't allowed, sentences about Aila are removed.
        - Paragraphs are kept; only runs of spaces are collapsed.
        """
        cleaned = (reply or "").strip()
        if not cleaned:
            return cleaned
        original = cleaned

        allowed = {url.rstrip("/").lower() for url in (source_urls or []) if url}
        if allow_link:
            allowed.add(AILA_WAITLIST_URL.rstrip("/").lower())

        def is_allowed(url: str) -> bool:
            return url.rstrip(".,;:!?)").rstrip("/").lower() in allowed

        def markdown_link(match: re.Match) -> str:
            text, target = match.group(1).strip(), match.group(2).strip()
            if re.match(r"https?://", text):
                # [https://...](https://...) is just a link: leave the bare URL for the rule below.
                return target if re.match(r"https?://", target) else text
            return match.group(0) if is_allowed(target) else text

        def bare_link(match: re.Match) -> str:
            return match.group(0) if is_allowed(match.group(2)) else ""

        def drop_promotion(line: str) -> str:
            sentences = re.split(r"(?<=[.!?])\s+", line)
            words = ("aila", "waitlist", "we're building", "working on")
            return " ".join(s for s in sentences if not any(word in s.lower() for word in words))

        paragraphs = []
        for paragraph in re.split(r"\n\s*\n", cleaned):
            lines = []
            for line in paragraph.split("\n"):
                line = re.sub(r"\[([^\]]*)\]\(([^)\s]*)\)", markdown_link, line)
                # A removed link takes the "at", "via", ":" or dash that introduced it.
                line = re.sub(
                    r"(\s*(?:\b(?:at|via)\s+)?[:\-\u2013\u2014]?\s*)(https?://[^\s)\]]+)", bare_link, line
                )
                line = re.sub(r"(?<![\w@/.])@[A-Za-z0-9_]{2,15}\b", "", line)
                if not allow_aila_mention:
                    line = drop_promotion(line)
                line = re.sub(r"[ \t]{2,}", " ", line)
                line = re.sub(r"[ \t]+([,.!?;:])", r"\1", line).strip()
                if line:
                    lines.append(line)
            if lines:
                paragraphs.append("\n".join(lines))
        cleaned = "\n\n".join(paragraphs)

        # If something was cut from the end, close the sentence again.
        if cleaned and cleaned != original and cleaned[-1].isalnum():
            cleaned += "."
        return cleaned

    def _record_outreach_outcome(self, lead: Dict[str, Any], planned_mention: bool, planned_link: bool, reply: str):
        lower_reply = (reply or "").lower()
        aila_mentioned = planned_mention and ("aila" in lower_reply or "we're building" in lower_reply or "working on" in lower_reply)
        link_included = planned_link and (AILA_WAITLIST_URL.lower() in lower_reply or "joinaila.com" in lower_reply)

        if aila_mentioned:
            self.promotional_mentions_used += 1
            if lead.get("source", "reddit") == "x":
                self.x_replies_generated += 1
                self.x_replies_by_user[lead.get("author", "")] += 1
            else:
                self.promo_replies_by_subreddit[lead.get("subreddit", "")] += 1
        if link_included:
            self.linked_replies_used += 1

        lead["subreddit_policy_mode"] = lead.get(
            "subreddit_policy_mode",
            self._get_policy_mode(lead.get("subreddit", ""), source=lead.get("source", "reddit")),
        )
        lead["promotion_allowed"] = planned_mention or planned_link
        lead["aila_mentioned"] = aila_mentioned
        lead["link_included"] = link_included

    def generate_reply(self, lead: Dict[str, Any]) -> str:
        """
        Generate single high-quality reply for a lead.

        Args:
            lead: Lead dict with title, selftext/comment_text, top_comments, lead_type

        Returns:
            Generated reply text
        """
        title = lead.get("title", "")
        lead_type = lead.get("lead_type", "post")
        source = lead.get("source", "reddit")

        # For comment leads, use comment_text; for post leads, use selftext
        if lead_type == "comment":
            text_content = lead.get("comment_text", "")
            username = lead.get("reddit_username", "unknown")
        else:
            text_content = lead.get("selftext", "")
            username = lead.get("author", "unknown")

        comments = lead.get("top_comments", [])
        comments_summary = get_comments_summary(comments)
        needs_grounding, source_group, _ = detect_grounding_need(lead)
        sources = gather_sources_for_lead(lead) if (ENABLE_REPLY_GROUNDING and needs_grounding) else []
        grounded_sources = format_sources_for_prompt(sources)
        outreach_plan = self._plan_outreach(lead)

        lead["reply_sources"] = sources
        flags = promotion_flags_for_mode(outreach_plan["policy_mode"])
        lead["promo_mode"] = flags["promo_mode"]
        lead["subreddit_policy_mode"] = flags["promo_mode"]
        lead["link_allowed"] = flags["link_allowed"]
        lead["mention_allowed"] = flags["mention_allowed"]
        lead["actionable_for_promotion"] = flags["actionable_for_promotion"]
        lead["promotion_allowed"] = outreach_plan["allow_aila_mention"] or outreach_plan["allow_link"]

        logger.info(f"Generating reply for {source}/{lead_type} by u/{username}: {title[:50]}...")
        if sources:
            logger.info(f"  Using {len(sources)} grounding sources ({source_group})")
        logger.info(
            "  Outreach mode: %s | mention=%s | link=%s",
            outreach_plan["policy_mode"],
            outreach_plan["allow_aila_mention"],
            outreach_plan["allow_link"],
        )

        # Generate single reply
        if source == "x":
            prompt = build_x_reply_prompt(
                text_content or title,
                grounded_sources=grounded_sources,
                needs_grounding=needs_grounding,
                allow_aila_mention=outreach_plan["allow_aila_mention"],
                allow_link=outreach_plan["allow_link"],
                style_variant=outreach_plan["style_variant"],
            )
            max_tokens = 180
        else:
            prompt = build_reply_prompt(
                title,
                text_content,
                comments_summary,
                lead_type,
                grounded_sources=grounded_sources,
                needs_grounding=needs_grounding,
                policy_mode=outreach_plan["policy_mode"],
                allow_aila_mention=outreach_plan["allow_aila_mention"],
                allow_link=outreach_plan["allow_link"],
                style_variant=outreach_plan["style_variant"],
            )
            max_tokens = 420
        reply = self.client.generate(
            prompt=prompt,
            system=SYSTEM_PROMPT,
            temperature=0.45,
            max_tokens=max_tokens,
        )

        if not reply and OLLAMA_FALLBACK_MODEL and OLLAMA_FALLBACK_MODEL != self.client.model:
            logger.warning(f"Primary model failed, retrying with fallback model: {OLLAMA_FALLBACK_MODEL}")
            fallback_client = OllamaClient(model=OLLAMA_FALLBACK_MODEL)
            reply = fallback_client.generate(
                prompt=prompt,
                system=SYSTEM_PROMPT,
                temperature=0.45,
                max_tokens=max_tokens,
            )

        reply = self._sanitize_reply(
            reply or "",
            allow_aila_mention=outreach_plan["allow_aila_mention"],
            allow_link=outreach_plan["allow_link"],
            source_urls=[source.get("url", "") for source in sources],
        )
        self._record_outreach_outcome(
            lead,
            planned_mention=outreach_plan["allow_aila_mention"],
            planned_link=outreach_plan["allow_link"],
            reply=reply,
        )

        if reply:
            logger.debug(f"  ✓ Reply generated ({len(reply)} chars)")
        else:
            logger.warning(f"  ✗ Reply generation failed")

        if source == "x" and X_DELAY_BETWEEN_GENERATIONS > 0:
            time.sleep(X_DELAY_BETWEEN_GENERATIONS)

        return reply or "[Generation failed]"

    def generate_for_multiple_leads(
        self,
        leads: List[Dict[str, Any]],
        max_leads: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Generate single reply for multiple leads.

        Args:
            leads: List of lead dicts
            max_leads: Maximum number to process

        Returns:
            Leads with 'reply' field added
        """
        logger.info(f"Generating replies for {min(len(leads), max_leads)} leads...")

        processed = []

        for i, lead in enumerate(leads[:max_leads], 1):
            logger.info(f"  [{i}/{min(len(leads), max_leads)}]")

            try:
                reply = self.generate_reply(lead)
                lead["reply"] = reply
                lead["has_reply"] = True
                processed.append(lead)

            except Exception as e:
                logger.error(f"  Error generating reply: {e}")
                lead["reply"] = "[Generation error]"
                lead["has_reply"] = False
                processed.append(lead)

        # Add remaining leads without replies
        for lead in leads[max_leads:]:
            lead["reply"] = None
            lead["has_reply"] = False
            processed.append(lead)

        logger.info(f"Reply generation complete: {sum(1 for l in processed if l.get('has_reply'))} successful")

        return processed


def test_reply_generation():
    """Test reply generation with a sample lead."""
    logger.info("Testing reply generation...")

    sample_lead = {
        "title": "Looking for a good travel planning app",
        "selftext": "I'm planning a 2-week trip to Europe and I'm overwhelmed. Too many apps for flights, hotels, itinerary. Anyone have recommendations for an all-in-one solution?",
        "lead_type": "post",
        "author": "traveler123",
        "top_comments": [
            {"score": 10, "body": "I feel you! I use like 5 different apps and it's chaos."},
            {"score": 5, "body": "TripIt is okay but not great for everything."},
        ],
    }

    generator = ReplyGenerator()
    reply = generator.generate_reply(sample_lead)

    logger.info("\n" + "=" * 60)
    logger.info("SAMPLE REPLY")
    logger.info("=" * 60)
    logger.info(f"\n{reply}\n")
    logger.info("=" * 60)

    return True

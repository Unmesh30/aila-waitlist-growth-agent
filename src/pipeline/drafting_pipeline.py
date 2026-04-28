"""
Drafting pipeline - generates reply drafts for qualified leads.

Uses local Ollama to generate single high-quality reply per lead.
"""

from typing import List, Dict, Any

from ..llm.reply_generator import ReplyGenerator
from ..llm.ollama_client import test_ollama_connection
from ..utils.logger import get_logger
from config.settings import MAX_LEADS_TO_DRAFT, REPLY_BATCH_SIZE
from config.sources import get_promo_mode, promotion_flags_for_mode

logger = get_logger(__name__)


def _apply_promo_policy(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Annotate lead with promotion policy flags and return it."""
    promo_mode = lead.get("promo_mode") or get_promo_mode(
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


def run_drafting_pipeline(
    leads: List[Dict[str, Any]],
    max_leads_to_draft: int | None = None,
) -> List[Dict[str, Any]]:
    """
    Run the reply drafting pipeline.

    Args:
        leads: List of qualified leads (dicts or ORM objects)
        max_leads_to_draft: Maximum leads to generate replies for (default from settings)

    Returns:
        Leads with single reply added to each
    """
    # Use configured default if not specified
    if max_leads_to_draft is None:
        max_leads_to_draft = MAX_LEADS_TO_DRAFT
    logger.info("=" * 60)
    logger.info("STARTING DRAFTING PIPELINE")
    logger.info("=" * 60)

    # Convert ORM objects to dicts if needed (防止 DetachedInstanceError)
    dict_leads = []
    for lead in leads:
        if isinstance(lead, dict):
            # Already a dict
            dict_leads.append(lead)
        else:
            # ORM object - convert to dict eagerly before session closes
            try:
                lead_dict = {
                    "title": lead.title,
                    "selftext": getattr(lead, 'selftext', ''),
                    "url": getattr(lead, 'url', ''),
                    "subreddit": getattr(lead, 'subreddit', ''),
                    "source": getattr(lead, 'source', 'reddit'),
                    "source_id": getattr(lead, 'source_id', None),
                    "author": getattr(lead, 'author', ''),
                    "score": getattr(lead, 'score', 0),
                    "num_comments": getattr(lead, 'num_comments', 0),
                    "created_utc": getattr(lead, 'created_utc', 0),
                    "lead_score": getattr(lead, 'lead_score', 0),
                    "top_comments": getattr(lead, 'top_comments', []),
                    "score_breakdown": getattr(lead, 'score_breakdown', {}),
                    "lead_type": getattr(lead, 'lead_type', 'post'),
                    "reddit_username": getattr(lead, 'reddit_username', getattr(lead, 'author', '')),
                    "comment_text": getattr(lead, 'comment_text', ''),
                    "subreddit_policy_mode": getattr(lead, 'subreddit_policy_mode', 'disallow_promo'),
                    "promotion_allowed": getattr(lead, 'promotion_allowed', False),
                    "link_included": getattr(lead, 'link_included', False),
                    "aila_mentioned": getattr(lead, 'aila_mentioned', False),
                }
                dict_leads.append(lead_dict)
                logger.debug(f"Converted ORM object to dict: {lead_dict.get('title', '')[:50]}")
            except AttributeError as e:
                logger.error(f"Failed to convert lead to dict: {e}")
                continue

    if not dict_leads:
        logger.warning("No valid leads to draft after conversion")
        return []

    dict_leads = [_apply_promo_policy(lead) for lead in dict_leads]
    before_policy_filter = len(dict_leads)
    dict_leads = [lead for lead in dict_leads if lead.get("actionable_for_promotion")]
    skipped = before_policy_filter - len(dict_leads)
    if skipped:
        logger.info(f"Promotion policy filter: skipped {skipped} non-actionable leads before drafting")

    if not dict_leads:
        logger.warning("No promotion-actionable leads to draft after policy filtering")
        return []

    logger.info(f"Converted {len(dict_leads)} leads to dicts for processing")

    # Check Ollama connection
    logger.info("\n[1/2] Checking Ollama connection...")
    if not test_ollama_connection():
        logger.error("Ollama is not available. Cannot generate final replies.")
        logger.error("Please ensure Ollama is running: ollama serve")
        return dict_leads

    # Generate replies
    logger.info(f"\n[2/2] Generating one final reply for top {max_leads_to_draft} leads...")
    generator = ReplyGenerator()
    leads_with_replies = []

    draft_targets = dict_leads[:max_leads_to_draft]
    for start in range(0, len(draft_targets), REPLY_BATCH_SIZE):
        end = min(start + REPLY_BATCH_SIZE, len(draft_targets))
        logger.info(f"  Batch {start // REPLY_BATCH_SIZE + 1}: leads {start + 1}-{end} of {len(draft_targets)}")
        batch_results = generator.generate_for_multiple_leads(
            draft_targets[start:end],
            max_leads=end - start,
        )
        leads_with_replies.extend(batch_results)

    for lead in dict_leads[max_leads_to_draft:]:
        lead["reply"] = None
        lead["has_reply"] = False
        leads_with_replies.append(lead)

    logger.info("=" * 60)
    logger.info(f"DRAFTING COMPLETE: {sum(1 for l in leads_with_replies if l.get('has_reply'))} leads with replies")
    logger.info("=" * 60)

    return leads_with_replies


def test_drafting():
    """Test drafting with a sample lead."""
    sample_lead = {
        "title": "Need help organizing my Europe trip",
        "selftext": "Planning a 3-week backpacking trip across Europe. So many apps for flights, hotels, itinerary... feeling overwhelmed. Any recommendations for an all-in-one solution?",
        "lead_score": 75.5,
        "lead_type": "post",
        "author": "testuser",
        "top_comments": [
            {"score": 12, "body": "Same here! Using too many apps is frustrating."},
        ],
    }

    logger.info("Testing drafting pipeline with sample lead...")
    leads_with_replies = run_drafting_pipeline([sample_lead], max_leads_to_draft=1)

    if leads_with_replies and leads_with_replies[0].get("reply"):
        reply = leads_with_replies[0]["reply"]
        logger.info("\n" + "=" * 60)
        logger.info("SAMPLE REPLY")
        logger.info("=" * 60)
        logger.info(f"\n{reply}\n")
        logger.info("=" * 60)

    return True

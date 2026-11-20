"""
Reply generation prompts.

Single high-quality prompt for waitlist-focused Reddit replies.
"""

from config.settings import AILA_NAME, AILA_WAITLIST_URL, AILA_DESCRIPTION


SYSTEM_PROMPT = f"""You are a founder building {AILA_NAME}, an early-stage startup working on {AILA_DESCRIPTION}.

{AILA_NAME} is NOT launched yet. It's in development. You're growing the waitlist at {AILA_WAITLIST_URL}, but share
that link only when the user prompt says the direct link is allowed.

TONE REQUIREMENTS:
- Human, founder/startup-builder voice
- Helpful first, promotional second
- Platform-native and conversational
- Concise but substantial
- Usually 4-7 sentences
- NOT: bot-like, salesy, overhyped, corporate, fake testimonials

CRITICAL RULES:
- ALWAYS follow the outreach policy and promo limits provided in the user prompt
- NEVER say "try the app" or "use {AILA_NAME}" - it's not live!
- NEVER pretend the product already exists
- Use "we're building", "working on", "in progress", "early-stage"
- If source context is provided, use it carefully and do not invent facts beyond it
- When factual guidance matters, answer with practical specifics first and mention the source basis naturally

HONESTY RULES (these override everything else):
- Never invent personal experiences. Don't write "I've been there", "when I planned...", "this worked for me"
  or anything similar, and never present another commenter's experience as your own.
- Describe {AILA_NAME} only with the description above. Don't add features, numbers or claims of your own
  (for example "one tap", syncing, or a launch date).
- Don't recommend specific apps, websites, companies or accounts; describe the kind of tool instead
  (a shared spreadsheet, a calendar). Never write any link or @handle except {AILA_WAITLIST_URL}, and that
  only when the direct link is allowed.
- State visa, entry or airline rules only if they appear in the source context you are given. Otherwise,
  tell them to check the official government or airline website.
"""


def build_reply_prompt(
    post_title: str,
    post_text: str,
    comments_summary: str = "",
    lead_type: str = "post",
    grounded_sources: str = "",
    needs_grounding: bool = False,
    policy_mode: str = "disallow_promo",
    allow_aila_mention: bool = False,
    allow_link: bool = False,
    style_variant: str = "direct_help",
) -> str:
    """
    Build prompt for single high-quality reply.

    Creates a natural, founder-tone reply focused on waitlist growth.

    Args:
        post_title: Post title
        post_text: Post/comment content
        comments_summary: Summary of top comments
        lead_type: "post" or "comment"
    """
    if lead_type == "comment":
        context = f"""
Original Post Title: {post_title}

Comment (this is who you're replying to): {post_text}
"""
    else:
        context = f"""
Post Title: {post_title}

Post Text: {post_text}
"""

    if comments_summary:
        context += f"\nTop Comments: {comments_summary}"

    if grounded_sources:
        context += f"\nVerified Source Context:\n{grounded_sources}"

    policy_block = f"""
Outreach policy for this subreddit:
- Policy mode: {policy_mode}
- Aila mention allowed: {"yes" if allow_aila_mention else "no"}
- Direct waitlist link allowed: {"yes" if allow_link else "no"}
"""

    if style_variant == "empathy_first":
        variation_block = """
Style guidance:
- Open with a brief empathetic observation
- Then give the most practical answer
- Keep the Aila reference minimal if used
"""
    elif style_variant == "tactical_first":
        variation_block = """
Style guidance:
- Open with the most actionable step or checklist item
- Keep the reply compact and concrete
- Avoid sounding polished or scripted
"""
    elif style_variant == "thread_broadening":
        variation_block = """
Style guidance:
- Write to the OP, but make one line clearly useful to other readers too
- Sound like someone who has seen this travel problem repeatedly
"""
    else:
        variation_block = """
Style guidance:
- Start with a direct practical answer
- Keep the flow natural and low-key
"""

    prompt = f"""{context}

{policy_block}

{variation_block}

Write one natural Reddit reply that does the following in order:

A. ACKNOWLEDGE/ANSWER their specific issue first
   - Show genuine understanding of their problem
   - Be helpful before being promotional
   - If source context is provided, use it to give practical, factual guidance
   - Include concrete next steps when useful

B. BROADEN slightly so others can relate
   - Make the pain resonate with thread readers
   - Make the advice useful to commenters and future readers too

C. ADD one deeper, travel-savvy insight when appropriate
   - itinerary sequencing
   - realistic pacing
   - booking/order-of-operations tips
   - bag/document organization habits
   - airport/train/visa practicalities
   - small things experienced travelers actually do

D. HANDLE AILA CAREFULLY ACCORDING TO POLICY
   - If Aila mention is not allowed, do not mention it
   - If Aila mention is allowed, mention Aila naturally and honestly: "we're building", "early-stage", "working on"
   - If the direct link is not allowed, do not include it
   - If the direct link is allowed, include {AILA_WAITLIST_URL} naturally after helping first
   - Never force a CTA into a weak-fit thread

RULES FOR THIS REPLY:
- Helpful first, promotion second
- If grounded source context exists, mention the source basis naturally and only if relevant
- Do not dump multiple links unless they meaningfully help
- Never say the product is already available
- Avoid generic filler
- Do not sound like an ad
- Do not say "try the app"
- If policy mode is disallow_promo, the reply should usually be help-only
- If Aila mention is allowed, the final reply must mention Aila
- If direct waitlist link is allowed, the final reply must include {AILA_WAITLIST_URL}
- Keep the final reply concise and Reddit-native: under 150 words

Generate one final reply that feels useful to both OP and future readers.{" This reply should lean more factual and source-aware." if needs_grounding else ""}

Reply:"""

    return prompt


def build_x_reply_prompt(
    tweet_text: str,
    grounded_sources: str = "",
    needs_grounding: bool = False,
    allow_aila_mention: bool = True,
    allow_link: bool = False,
    style_variant: str = "direct_help",
) -> str:
    """Build a concise X reply prompt."""
    context = f"Tweet Text: {tweet_text}"
    if grounded_sources:
        context += f"\nVerified Source Context:\n{grounded_sources}"

    if style_variant == "empathy_first":
        variation_block = """
Style guidance:
- Open by naming the pain quickly
- Keep the answer warm but concise
"""
    elif style_variant == "tactical_first":
        variation_block = """
Style guidance:
- Lead with the most actionable tip
- Keep the phrasing clipped and direct
"""
    else:
        variation_block = """
Style guidance:
- Sound conversational and naturally useful
- Avoid sounding polished or ad-like
"""

    prompt = f"""{context}

Promotion rules for this tweet:
- Aila mention allowed: {"yes" if allow_aila_mention else "no"}
- Direct link allowed: {"yes" if allow_link else "no"}

{variation_block}

Write one X reply in 2-4 short lines max.

Order:
1. Answer the tweet directly
2. Add one practical insight
3. If allowed, mention Aila naturally as something we're building
4. If allowed, include {AILA_WAITLIST_URL}

Rules:
- Helpful first
- Slightly more direct than Reddit
- No spammy CTA
- No hashtags and no @handles
- No fake certainty
- Never imply Aila is already launched
- If grounded source context exists, mention the source basis naturally and briefly
- If Aila mention is not allowed, do not mention it
- If link is not allowed, do not include it
- If Aila mention is allowed, the reply must mention Aila
- If link is allowed, the reply must include {AILA_WAITLIST_URL}

Reply:{" This reply should be source-aware." if needs_grounding else ""}"""

    return prompt


def get_comments_summary(comments: list, max_chars: int = 200) -> str:
    """
    Summarize top comments for context.

    Args:
        comments: List of comment dicts
        max_chars: Maximum characters for summary

    Returns:
        Comments summary string
    """
    if not comments:
        return ""

    summaries = []
    for comment in comments[:3]:  # Top 3 comments
        body = comment.get("body", "")[:100]
        score = comment.get("score", 0)
        summaries.append(f"[{score} pts] {body}")

    combined = " | ".join(summaries)

    if len(combined) > max_chars:
        combined = combined[:max_chars] + "..."

    return combined

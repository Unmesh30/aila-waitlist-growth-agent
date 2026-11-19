"""
Streamlit dashboard for reviewing and managing waitlist leads.

Provides a simple interface to:
- View discovered leads sorted by score
- Review generated replies
- Mark leads as approved/rejected/posted
- Track statistics
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from src.storage.repository import LeadRepository
from src.storage.models import LeadStatus
from src.utils.date_utils import format_relative_time
from src.utils.text_utils import truncate
from config.settings import AILA_WAITLIST_URL, REVIEW_QUEUE_LIMIT

# Page config
st.set_page_config(
    page_title="Aila Waitlist Agent",
    page_icon="✈️",
    layout="wide",
)


def init_repository():
    """Dashboard no longer keeps a persistent SQLite connection in session state."""
    return None


def with_repository(fn, *args, **kwargs):
    """Run a repository operation with a short-lived connection."""
    repo = LeadRepository()
    try:
        return fn(repo, *args, **kwargs)
    finally:
        repo.close()


def load_leads(status_filter=None):
    """Load leads from database."""
    def _load(repo):
        if status_filter == "All":
            return repo.get_all_leads(limit=REVIEW_QUEUE_LIMIT)
        elif status_filter == "New":
            return repo.get_new_leads(limit=REVIEW_QUEUE_LIMIT)
        elif status_filter == "Approved":
            return repo.get_approved_leads(limit=REVIEW_QUEUE_LIMIT)
        elif status_filter == "Posted":
            return repo.db.get_leads_by_status(LeadStatus.POSTED, limit=REVIEW_QUEUE_LIMIT)
        elif status_filter == "Rejected":
            return repo.db.get_leads_by_status(LeadStatus.REJECTED, limit=REVIEW_QUEUE_LIMIT)
        else:
            return repo.get_all_leads(limit=REVIEW_QUEUE_LIMIT)

    return with_repository(_load)


def update_lead_status(post_id, new_status, notes=""):
    """Update lead status."""
    def _update(repo):
        if new_status == "approved":
            repo.approve_lead(post_id, notes)
        elif new_status == "rejected":
            repo.reject_lead(post_id, notes)
        elif new_status == "posted":
            repo.mark_posted(post_id, notes)

    return with_repository(_update)


def render_statistics():
    """Render statistics sidebar."""
    stats = with_repository(lambda repo: repo.get_statistics())

    st.sidebar.title("📊 Statistics")

    st.sidebar.metric("Total Leads", stats["total_leads"])
    st.sidebar.metric("Avg Score", f"{stats['avg_lead_score']:.1f}")

    st.sidebar.write("**By Status:**")
    by_status = stats.get("by_status", {})
    for status, count in by_status.items():
        st.sidebar.write(f"- {status.title()}: {count}")

    by_source = stats.get("by_source", {})
    if by_source:
        st.sidebar.write("**By Source:**")
        for source, count in by_source.items():
            st.sidebar.write(f"- {source.title()}: {count}")


def render_lead_card(lead):
    """Render a single lead card."""
    post_id = lead["post_id"]
    title = lead["title"]
    subreddit = lead["subreddit"]
    score = lead["lead_score"]
    url = lead["url"]
    status = lead["status"]
    source = lead.get("source", "reddit")
    author = lead.get("author", "")
    reddit_score = lead.get("score", 0)
    num_comments = lead.get("num_comments", 0)
    created_utc = lead.get("created_utc")

    # New fields for comment tracking
    lead_type = lead.get("lead_type", "post")
    reddit_username = lead.get("reddit_username", author)
    comment_text = lead.get("comment_text", "")
    parent_post_url = lead.get("parent_post_url", "")

    # Color code by score
    if score >= 70:
        score_color = "🟢"
    elif score >= 50:
        score_color = "🟡"
    else:
        score_color = "🔴"

    # Lead type badge
    if lead_type == "comment":
        type_badge = "💬 COMMENT LEAD"
    elif source == "x":
        type_badge = "𝕏 TWEET LEAD"
    else:
        type_badge = "📝 POST LEAD"

    # Header
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        st.markdown(f"### {score_color} [{score:.1f}] {title}")
        location_label = f"r/{subreddit}" if source == "reddit" else "X"
        reply_handle = f"@{reddit_username}" if source == "x" else f"u/{reddit_username}"
        st.caption(f"{type_badge} · {location_label} · Reply to: **{reply_handle}**")

        if source == "x":
            st.caption(f"Tweet by @{author} · {reddit_score} likes, {num_comments} replies")
        elif lead_type == "post":
            st.caption(f"Posted by u/{author} · {reddit_score} pts, {num_comments} comments")
        else:
            st.caption(f"Comment by u/{reddit_username} · {reddit_score} pts · Post by u/{author}")

        if created_utc:
            relative_time = format_relative_time(created_utc)
            st.caption(f"Posted: {relative_time}")

    with col2:
        st.metric("Status", status.upper())

    with col3:
        button_label = "View on X" if source == "x" else "View on Reddit"
        st.link_button(button_label, url, use_container_width=True)

    # Content display (different for posts vs comments)
    if source == "x":
        if lead.get("selftext"):
            with st.expander("𝕏 Tweet Content"):
                st.write(truncate(lead.get("selftext", ""), 500))
    elif lead_type == "comment":
        if comment_text:
            with st.expander("💬 Comment Content (Lead Source)"):
                st.write(truncate(comment_text, 500))

        if parent_post_url:
            st.caption(f"[View original post]({parent_post_url})")
    else:
        selftext = lead.get("selftext", "")
        if selftext:
            with st.expander("📄 Post Content"):
                st.write(truncate(selftext, 500))

    # Score breakdown
    score_breakdown = lead.get("score_breakdown", {})
    if score_breakdown:
        with st.expander("📈 Score Breakdown (Rules-Based)"):
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Pain Points", f"{score_breakdown.get('pain_point_score', 0):.1f}")
            col2.metric("Request", f"{score_breakdown.get('request_score', 0):.1f}")
            col3.metric("Engagement", f"{score_breakdown.get('engagement_score', 0):.1f}")
            col4.metric("Recency", f"{score_breakdown.get('recency_score', 0):.1f}")
            col5.metric("Quality", f"{score_breakdown.get('quality_score', 0):.1f}")
            if source == "x":
                st.caption(
                    f"Tweet signals: likes={reddit_score}, replies={num_comments}, x_signal={score_breakdown.get('x_signal_score', 0):.1f}"
                )

            reason = score_breakdown.get("score_reason", "")
            if reason:
                st.caption(f"**Why:** {reason}")

            keywords = score_breakdown.get("matched_keywords", [])
            if keywords:
                st.caption(f"**Keywords:** {', '.join(keywords)}")

    # Reply (single high-quality reply)
    reply = lead.get("reply")
    reply_sources = lead.get("reply_sources", [])
    promo_mode = lead.get("promo_mode") or lead.get("subreddit_policy_mode", "disallowed_or_unclear")
    link_allowed = lead.get("link_allowed", False)
    mention_allowed = lead.get("mention_allowed", False)
    actionable_for_promotion = lead.get("actionable_for_promotion", False)
    promotion_allowed = lead.get("promotion_allowed", False)
    link_included = lead.get("link_included", False)
    aila_mentioned = lead.get("aila_mentioned", False)

    with st.expander("🛡️ Outreach Safety"):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Promo Mode", promo_mode)
        col2.metric("Actionable", "Yes" if actionable_for_promotion else "No")
        col3.metric("Mention Allowed", "Yes" if mention_allowed else "No")
        col4.metric("Link Allowed", "Yes" if link_allowed else "No")

        col5, col6, col7 = st.columns(3)
        col5.metric("Promo Allowed", "Yes" if promotion_allowed else "No")
        col6.metric("Aila Mentioned", "Yes" if aila_mentioned else "No")
        col7.metric("Link Included", "Yes" if link_included else "No")

    if reply:
        st.write("**💬 Generated Reply:**")
        st.text_area(
            "Reply",
            reply,
            height=150,
            key=f"reply_{post_id}",
            label_visibility="collapsed",
            help="Copy this reply to use on the source platform"
        )

        if reply_sources:
            with st.expander("🔎 Sources Used"):
                for source in reply_sources:
                    title = source.get("title", "Untitled source")
                    url = source.get("url", "")
                    snippet = source.get("snippet", "")
                    domain = source.get("domain", "")

                    if url:
                        st.markdown(f"**[{title}]({url})**")
                    else:
                        st.markdown(f"**{title}**")
                    if domain:
                        st.caption(domain)
                    if snippet:
                        st.write(snippet)
    else:
        st.info("💭 No reply generated yet")

    # Actions
    st.write("**Actions:**")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("✅ Approve", key=f"approve_{post_id}", use_container_width=True):
            update_lead_status(post_id, "approved")
            st.success("Approved!")
            st.rerun()

    with col2:
        if st.button("❌ Reject", key=f"reject_{post_id}", use_container_width=True):
            update_lead_status(post_id, "rejected")
            st.success("Rejected!")
            st.rerun()

    with col3:
        if st.button("📤 Mark Posted", key=f"posted_{post_id}", use_container_width=True):
            update_lead_status(post_id, "posted")
            st.success("Marked as posted!")
            st.rerun()

    with col4:
        if st.button("🔗 Copy URL", key=f"copy_{post_id}", use_container_width=True):
            st.code(url, language=None)

    st.divider()


def _parse_created_utc(lead):
    """Parse created_utc into a sortable float timestamp, or None if invalid."""
    created_utc = lead.get("created_utc")
    if created_utc is None:
        return None

    try:
        return float(created_utc)
    except (TypeError, ValueError):
        return None


def main():
    """Main app."""
    # Initialize
    init_repository()

    # Header
    st.title("✈️ Aila Waitlist Agent")
    st.caption(f"Find and engage potential users · Waitlist: {AILA_WAITLIST_URL}")

    # Sidebar
    render_statistics()

    st.sidebar.divider()

    # Filters
    st.sidebar.title("🔍 Filters")

    status_filter = st.sidebar.selectbox(
        "Status",
        ["All", "New", "Approved", "Rejected", "Posted"],
        index=1,
    )

    source_filter = st.sidebar.selectbox(
        "Source",
        ["All", "Reddit", "X"],
        index=0,
    )

    promo_filter = st.sidebar.selectbox(
        "Promotion",
        ["All", "Actionable Only", "Link Allowed Only", "Mention Only"],
        index=1,
    )

    # Load leads
    leads = load_leads(status_filter)
    if source_filter != "All":
        expected_source = "reddit" if source_filter == "Reddit" else "x"
        leads = [lead for lead in leads if lead.get("source", "reddit") == expected_source]
    if promo_filter == "Actionable Only":
        leads = [lead for lead in leads if lead.get("actionable_for_promotion")]
    elif promo_filter == "Link Allowed Only":
        leads = [lead for lead in leads if lead.get("promo_mode") == "link_allowed" or lead.get("link_allowed")]
    elif promo_filter == "Mention Only":
        leads = [lead for lead in leads if lead.get("promo_mode") == "mention_only"]

    # Main content
    st.header(f"{status_filter} Leads ({len(leads)})")

    if not leads:
        st.info(f"No {status_filter.lower()} leads found. Run the pipeline to discover new leads.")
        st.code("python3 run_pipeline.py", language="bash")
        return

    # Sort options
    sort_by = st.selectbox(
        "Sort by",
        ["Most Recent", "Link Allowed First", "High Score", "Oldest First"],
        index=0,
    )

    if sort_by == "High Score":
        leads = sorted(leads, key=lambda x: x["lead_score"], reverse=True)
    elif sort_by == "Most Recent":
        leads = sorted(
            leads,
            key=lambda lead: (
                _parse_created_utc(lead) is None,
                -_parse_created_utc(lead) if _parse_created_utc(lead) is not None else 0,
            ),
        )
    elif sort_by == "Oldest First":
        leads = sorted(
            leads,
            key=lambda lead: (
                _parse_created_utc(lead) is None,
                _parse_created_utc(lead) if _parse_created_utc(lead) is not None else 0,
            ),
        )
    elif sort_by == "Link Allowed First":
        leads = sorted(
            leads,
            key=lambda lead: (
                0 if (lead.get("promo_mode") == "link_allowed" or lead.get("link_allowed")) else 1,
                _parse_created_utc(lead) is None,
                -_parse_created_utc(lead) if _parse_created_utc(lead) is not None else 0,
                -float(lead.get("lead_score", 0) or 0),
            ),
        )

    # Render leads
    for lead in leads:
        render_lead_card(lead)


if __name__ == "__main__":
    main()

"""Export the demo run as a one-page static site (the live demo on GitHub Pages).

    python3 run_pipeline.py --demo
    python3 -m demo.export_site --out site

Everything on the page comes from the demo run: the leads, scores and replies stored in
data/demo/demo_leads.db, plus the bundled fixtures for what the guardrails dropped.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.scoring import SCORING_WEIGHTS  # noqa: E402
from config.sources import get_promo_mode  # noqa: E402
from demo import DEMO_DATABASE, FIXTURES  # noqa: E402
from src.llm.source_grounder import OFFICIAL_DOMAIN_GROUPS, _is_allowed_domain  # noqa: E402

REPO_URL = "https://github.com/Unmesh30/aila-waitlist-growth-agent"
COMPONENTS = [
    ("pain_point_score", "Pain points", "pain_points"),
    ("request_score", "Requests", "request"),
    ("engagement_score", "Engagement", "engagement"),
    ("recency_score", "Recency", "recency"),
    ("quality_score", "Quality", "quality"),
]


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_leads(db_path: Path) -> list[dict]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    leads = [dict(row) for row in con.execute("SELECT * FROM leads")]
    con.close()
    for lead in leads:
        lead["lead_score"] = _num(lead.get("lead_score"))
        lead["breakdown"] = json.loads(lead.get("score_breakdown") or "{}")
        lead["sources"] = json.loads(lead.get("reply_sources") or "[]")
    return sorted(leads, key=lambda lead: lead["lead_score"], reverse=True)


def dropped_by_policy() -> list[dict]:
    posts = json.loads((FIXTURES / "reddit_posts.json").read_text(encoding="utf-8"))
    return [p for p in posts if get_promo_mode(p.get("subreddit", "")) == "disallowed_or_unclear"]


def grounding_summary(leads: list[dict]) -> tuple[list[str], list[tuple[str, str]]]:
    used = sorted({source.get("domain") or urlparse(source["url"]).netloc for lead in leads for source in lead["sources"]})
    allowlist = sorted({domain for group in OFFICIAL_DOMAIN_GROUPS.values() for domain in group})
    rejected = []
    for _title, url in json.loads((FIXTURES / "search_results.json").read_text(encoding="utf-8")):
        domain = urlparse(url).netloc.lower()
        if domain in used or _is_allowed_domain(domain, allowlist):
            continue
        lookalike = next((a for a in allowlist if domain.endswith(a)), None)
        reason = f"look-alike: ends in “{lookalike}” but isn’t it" if lookalike else "not an official source"
        rejected.append((domain, reason))
    return used, rejected


def age_label(hours) -> str:
    hours = _num(hours, None)
    if hours is None:
        return ""
    if hours < 48:
        return f"{hours:.0f} h old when scored"
    return f"{hours / 24:.0f} days old when scored"


def render_breakdown(lead: dict) -> str:
    b = lead["breakdown"]
    if lead.get("lead_type") == "comment" or b.get("pain_point_score") is None:
        reason = b.get("score_reason", "").replace("Comment lead: ", "")
        return (
            '<p class="note">Comment leads are scored on the comment’s own words (shared pain, asks for '
            f"recommendations): <strong>{esc(reason)}</strong>.</p>"
        )
    rows = []
    for key, label, weight_key in COMPONENTS:
        value = _num(b.get(key))
        weight = round(SCORING_WEIGHTS[weight_key] * 100)
        rows.append(
            f'<div class="bar-row"><span class="bar-label">{label} <span class="muted">×{weight}%</span></span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{max(0.0, min(100.0, value)):.0f}%"></span></span>'
            f'<span class="bar-value">{value:.0f}</span></div>'
        )
    extras = ["weighted sum of the five scores"]
    if lead.get("source") == "x" and _num(b.get("x_signal_score")):
        extras.append(f"+ 0.35 × X signal ({_num(b.get('x_signal_score')):.0f})")
    modifier = _num(b.get("subreddit_modifier"))
    if modifier:
        extras.append(f"{'+' if modifier > 0 else '−'} {abs(modifier):.0f} for the community")
    extras.append("capped at 100")
    return (
        '<div class="bars">' + "".join(rows) + "</div>"
        f'<p class="note">Total = {esc(", ".join(extras))}.</p>'
        f'<p class="note">Why: {esc(b.get("score_reason", ""))}</p>'
    )


def render_card(lead: dict, index: int) -> str:
    source = lead.get("source", "reddit")
    lead_type = lead.get("lead_type", "post")
    if source == "x":
        where, who, kind = "X", f"@{lead.get('author', '')}", "Post"
    else:
        where, kind = f"r/{lead.get('subreddit', '')}", "Comment" if lead_type == "comment" else "Post"
        who = f"u/{lead.get('reddit_username') or lead.get('author', '')}"
    mode = lead.get("promo_mode") or lead.get("subreddit_policy_mode")
    if mode == "link_allowed":
        policy = '<span class="tag tag-link">Link allowed</span>'
    else:
        policy = '<span class="tag tag-mention">Mention only · link removed</span>'

    if lead_type == "comment":
        original = (
            f'<blockquote>{esc(lead.get("comment_text"))}</blockquote>'
            '<p class="note">This lead is a comment under the post titled above.</p>'
        )
    elif (lead.get("selftext") or "").strip() and lead.get("selftext") != lead.get("title"):
        original = f"<blockquote>{esc(lead.get('selftext'))}</blockquote>"
    else:
        original = ""

    sources = ""
    if lead["sources"]:
        links = ", ".join(
            f'<a href="{esc(s["url"])}">{esc(s.get("domain") or urlparse(s["url"]).netloc)}</a>' for s in lead["sources"]
        )
        sources = f'<p class="note">Facts grounded only in: {links}</p>'

    reply = esc(lead.get("reply", ""))
    reply = reply.replace(
        "[Demo reply: placeholder text, not written by a model]",
        '<span class="placeholder">[Demo reply: placeholder text, not written by a model]</span>',
    )
    score = lead["lead_score"]
    band = "high" if score >= 70 else "mid" if score >= 50 else "low"
    return f"""
    <article class="card" id="lead-{index}" data-state="waiting">
      <div class="card-head">
        <div class="score score-{band}" aria-label="Lead score {score:.1f} out of 100">{score:.1f}</div>
        <div class="card-title">
          <h3>{esc(lead.get('title'))}</h3>
          <p class="meta">{esc(kind)} · {esc(where)} · {esc(who)} · {esc(age_label(lead['breakdown'].get('age_hours')))} {policy}</p>
        </div>
      </div>
      {original}
      <details>
        <summary>Score breakdown</summary>
        {render_breakdown(lead)}
      </details>
      <div class="reply">
        <p class="reply-label">Drafted reply</p>
        <p>{reply}</p>
        {sources}
      </div>
      <div class="actions">
        <button type="button" class="btn btn-approve" data-action="approved" aria-pressed="false">✓ Approve</button>
        <button type="button" class="btn btn-reject" data-action="rejected" aria-pressed="false">✕ Reject</button>
        <span class="state" aria-live="polite">Waiting for review</span>
      </div>
    </article>"""


CSS = """
:root { --ink:#1f2328; --muted:#59636e; --line:#d1d9e0; --bg:#f6f8fa; --card:#ffffff; --accent:#1f6feb;
        --accent-soft:#ddf4ff; --ok:#1a7f37; --ok-soft:#dafbe1; --no:#cf222e; --no-soft:#ffebe9; --warn-soft:#fff8c5; }
* { box-sizing: border-box; }
body { margin:0; font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       color:var(--ink); background:var(--bg); }
a { color:var(--accent); }
.wrap { max-width: 980px; margin: 0 auto; padding: 32px 20px 56px; }
header h1 { font-size: 30px; line-height:1.2; margin: 0 0 8px; }
.lede { font-size: 18px; margin: 0 0 10px; }
.byline, .muted, .note { color: var(--muted); }
.byline { margin: 0 0 14px; }
.notice { background: var(--warn-soft); border:1px solid #d4a72c55; border-radius: 8px; padding: 10px 14px; font-size: 14px; }
h2 { font-size: 20px; margin: 36px 0 12px; }
.tiles { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; }
.tile { background: var(--card); border:1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.tile .num { font-size: 30px; font-weight: 650; line-height: 1.1; font-variant-numeric: tabular-nums; }
.tile .label { color: var(--muted); font-size: 14px; }
.guards { background: var(--card); border:1px solid var(--line); border-radius: 10px; padding: 6px 18px 6px 38px; margin:0; }
.guards li { margin: 10px 0; padding-left: 4px; }
.queue-head { display:flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.counts { color: var(--muted); font-size: 14px; font-variant-numeric: tabular-nums; }
.card { background: var(--card); border:1px solid var(--line); border-radius: 12px; padding: 16px 18px; margin: 12px 0; }
.card[data-state="approved"] { border-color: var(--ok); box-shadow: inset 4px 0 0 var(--ok); }
.card[data-state="rejected"] { border-color: var(--no); box-shadow: inset 4px 0 0 var(--no); opacity: .8; }
.card-head { display:flex; gap: 14px; align-items: flex-start; }
.score { flex: 0 0 auto; min-width: 58px; text-align:center; font-weight: 700; font-variant-numeric: tabular-nums;
         border-radius: 8px; padding: 6px 8px; font-size: 18px; }
.score-high { background: #0a3069; color: #fff; }
.score-mid { background: #54aeff; color: #0a3069; }
.score-low { background: var(--accent-soft); color: #0a3069; }
.card-title h3 { font-size: 17px; margin: 2px 0 4px; line-height: 1.35; }
.meta { margin: 0; color: var(--muted); font-size: 14px; }
.tag { display:inline-block; font-size: 12px; font-weight: 600; border-radius: 999px; padding: 1px 9px; margin-left: 4px;
       border: 1px solid var(--line); color: var(--ink); background: var(--bg); white-space: nowrap; }
.tag-link::before { content: "🔗 "; }
.tag-mention::before { content: "💬 "; }
blockquote { margin: 12px 0 0; padding: 8px 12px; border-left: 3px solid var(--line); color: #393f46; background: var(--bg);
             border-radius: 0 6px 6px 0; }
details { margin-top: 12px; }
summary { cursor: pointer; color: var(--accent); font-weight: 600; font-size: 15px; }
.bars { margin: 10px 0 6px; display:grid; gap: 6px; }
.bar-row { display:grid; grid-template-columns: 170px 1fr 40px; gap: 10px; align-items:center; font-size: 14px; }
.bar-track { height: 10px; background: #eaeef2; border-radius: 999px; overflow:hidden; }
.bar-fill { display:block; height: 100%; background: var(--accent); border-radius: 999px; }
.bar-value { text-align:right; font-variant-numeric: tabular-nums; }
.note { font-size: 14px; margin: 6px 0 0; }
.reply { margin-top: 14px; background: var(--bg); border:1px solid var(--line); border-radius: 8px; padding: 10px 14px; }
.reply p { margin: 0; }
.reply-label { font-size: 12px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--muted); margin-bottom: 4px !important; }
.placeholder { color: var(--muted); font-style: italic; }
.actions { display:flex; gap: 10px; align-items:center; margin-top: 14px; flex-wrap: wrap; }
.btn { font: inherit; font-size: 15px; font-weight: 600; border-radius: 8px; padding: 7px 14px; cursor: pointer;
       border: 1px solid var(--line); background: var(--card); color: var(--ink); }
.btn-approve:hover, .btn-approve[aria-pressed="true"] { background: var(--ok-soft); border-color: var(--ok); color: var(--ok); }
.btn-reject:hover, .btn-reject[aria-pressed="true"] { background: var(--no-soft); border-color: var(--no); color: var(--no); }
.btn:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
.state { color: var(--muted); font-size: 14px; }
ol.steps { background: var(--card); border:1px solid var(--line); border-radius: 10px; padding: 12px 18px 12px 38px; margin: 0; }
ol.steps li { margin: 6px 0; }
footer { margin-top: 36px; color: var(--muted); font-size: 14px; border-top: 1px solid var(--line); padding-top: 14px; }
@media (max-width: 720px) {
  .tiles { grid-template-columns: repeat(2, minmax(0,1fr)); }
  .bar-row { grid-template-columns: 120px 1fr 34px; }
  header h1 { font-size: 25px; }
}
"""

JS = """
(function () {
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var labels = { approved: 'Approved — ready to post by hand', rejected: 'Rejected', waiting: 'Waiting for review' };
  function refresh() {
    var c = { waiting: 0, approved: 0, rejected: 0 };
    cards.forEach(function (card) { c[card.getAttribute('data-state')] += 1; });
    document.getElementById('counts').textContent =
      'Waiting ' + c.waiting + ' · Approved ' + c.approved + ' · Rejected ' + c.rejected;
  }
  cards.forEach(function (card) {
    card.querySelectorAll('.btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var next = card.getAttribute('data-state') === btn.dataset.action ? 'waiting' : btn.dataset.action;
        card.setAttribute('data-state', next);
        card.querySelectorAll('.btn').forEach(function (b) {
          b.setAttribute('aria-pressed', String(b.dataset.action === next));
        });
        card.querySelector('.state').textContent = labels[next];
        refresh();
      });
    });
  });
  refresh();
})();
"""


def build_page(leads: list[dict]) -> str:
    dropped = dropped_by_policy()
    used, rejected = grounding_summary(leads)
    link_removed = sum(
        1 for lead in leads if lead.get("promo_mode") == "mention_only" and "joinaila.com" not in (lead.get("reply") or "")
    )
    link_kept = sum(
        1 for lead in leads if lead.get("promo_mode") == "link_allowed" and "joinaila.com" in (lead.get("reply") or "")
    )
    candidates = len(leads) + len(dropped)
    dropped_items = "".join(
        f"<li>“{esc(p['title'])}” <span class='muted'>(r/{esc(p['subreddit'])})</span></li>" for p in dropped
    )
    rejected_text = " and ".join(f"<strong>{esc(d)}</strong> ({esc(r)})" for d, r in rejected)
    used_text = " and ".join(f"<strong>{esc(d)}</strong>" for d in used)
    cards = "".join(render_card(lead, i + 1) for i, lead in enumerate(leads))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aila Waitlist Agent — live demo</title>
<meta name="description" content="Finds people asking for help with trip planning on Reddit and X, scores each post 0–100 and drafts a reply that a person approves before anything is posted.">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Aila Waitlist Agent — live demo</h1>
  <p class="lede">Finds people asking for help with trip planning on Reddit and X, scores each post 0–100, and drafts a reply
  that a person approves before anything is posted.</p>
  <p class="byline">Built by Unmesh Achar during his internship at Lunar Guide (Feb–Jun 2026) to grow the waitlist for Aila,
  its AI travel planner · <a href="{REPO_URL}">Code on GitHub</a></p>
  <p class="notice">This page is the real pipeline’s output on anonymised sample posts (<code>run_pipeline.py --demo</code>).
  The language model is replaced by a stand-in, so the replies are marked as placeholders. The buttons below only change this page.</p>
</header>

<h2>This run at a glance</h2>
<div class="tiles">
  <div class="tile"><div class="num">{candidates}</div><div class="label">candidates scored</div></div>
  <div class="tile"><div class="num">{len(dropped)}</div><div class="label">dropped by community rules</div></div>
  <div class="tile"><div class="num">{len(leads)}</div><div class="label">in the review queue</div></div>
  <div class="tile"><div class="num">0</div><div class="label">posted automatically</div></div>
</div>

<h2>What the guardrails did</h2>
<ul class="guards">
  <li><strong>Dropped {len(dropped)} posts</strong> from communities that don’t allow promotion, so they never reached the queue:<ul>{dropped_items}</ul></li>
  <li><strong>Kept only official sources</strong> for facts: replies cite {used_text}. The search also returned {rejected_text}, and the allowlist rejected them.</li>
  <li><strong>Removed the waitlist link from {link_removed} replies</strong> in communities that allow a mention but not a link, and kept it in {link_kept} replies on X.</li>
  <li><strong>Posted nothing.</strong> Every reply waits for a person to approve or reject it.</li>
</ul>

<div class="queue-head">
  <h2>Review queue, highest score first</h2>
  <span class="counts" id="counts" aria-live="polite"></span>
</div>
{cards}

<h2>How it works</h2>
<ol class="steps">
  <li>Collect recent posts from travel communities on Reddit and from X.</li>
  <li>Pull the top comments under promising posts and keep those that ask for help.</li>
  <li>Score each lead 0–100: pain points 30%, requests 25%, engagement 20%, recency 15%, quality 10%.</li>
  <li>Apply each community’s rules: a link, a mention only, or no promotion at all.</li>
  <li>Ground any facts (visa, airline rules) in an allowlist of official domains.</li>
  <li>Draft one reply per lead with a local language model, then enforce the community’s rules on the text again.</li>
  <li>Queue everything for a person to approve or reject in the review dashboard.</li>
</ol>

<footer>
  Generated from a demo run of the pipeline on {date.today():%d %B %Y}. Source code, tests and setup:
  <a href="{REPO_URL}">github.com/Unmesh30/aila-waitlist-growth-agent</a>.
</footer>
</div>
<script>{JS}</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(ROOT / DEMO_DATABASE), help="demo database to export")
    parser.add_argument("--out", default="site", help="output folder")
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        sys.exit(f"{db} not found: run `python3 run_pipeline.py --demo` first")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(build_page(load_leads(db)), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Wrote {out / 'index.html'}")


if __name__ == "__main__":
    main()

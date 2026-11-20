"""Export a demo run as a one-page static site (the interactive demo on GitHub Pages).

    python3 run_pipeline.py --demo
    python3 -m demo.export_site --out site

Everything on the page comes from the demo run: the leads, scores and replies stored in
data/demo/demo_leads.db, the run report in data/demo/run_report.json (every candidate and
what happened to it), and the recorded model replies in demo/fixtures/recorded_replies.json.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.scoring import SCORING_WEIGHTS  # noqa: E402
from demo import DEMO_DATABASE, FIXTURES, RUN_REPORT, load_recorded_replies  # noqa: E402
from src.llm.source_grounder import OFFICIAL_DOMAIN_GROUPS, _is_allowed_domain  # noqa: E402

REPO_URL = "https://github.com/Unmesh30/aila-waitlist-growth-agent"
PLACEHOLDER = "[Demo reply: placeholder text, not written by a model]"
URL_RE = re.compile(r"https?://\S+")
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


def load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def grounding_summary(leads: list[dict]) -> tuple[list[str], list[tuple[str, str]]]:
    used = sorted({s.get("domain") or urlparse(s["url"]).netloc for lead in leads for s in lead["sources"]})
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


def age_text(hours) -> str:
    hours = _num(hours, None)
    if hours is None:
        return ""
    return f"{hours:.0f} h old" if hours < 48 else f"{hours / 24:.0f} days old"


def where_text(item: dict) -> str:
    return "X" if item.get("source") == "x" else f"r/{item.get('subreddit', '')}"


def said_no_groups(report: dict) -> list[tuple[str, str, list[str]]]:
    """Group everything the run turned down, using the run report written during the demo run."""
    candidates = report.get("candidates", [])
    target = report.get("target_final_leads")
    policy, too_old, cut = [], [], []
    for c in sorted(candidates, key=lambda c: -c["lead_score"]):
        if c["kept"]:
            continue
        label = f"“{esc(c['title'])}” <span class='muted'>({esc(where_text(c))} · score {c['lead_score']:.0f}"
        if c.get("promo_mode") == "disallowed_or_unclear":
            policy.append(label + ")</span>")
        elif c.get("recency_bucket") == 4:
            too_old.append(label + f" · {esc(age_text(c['age_hours']))})</span>")
        else:
            cut.append(label + ")</span>")
    comments = [
        f"“{esc(c['body'])}” <span class='muted'>(r/{esc(c['subreddit'])} · score {c['score']:.0f})</span>"
        for c in report.get("comments", [])
        if not c["became_lead"]
    ]
    groups = []
    if policy:
        groups.append((f"Communities that don’t allow promotion ({len(policy)})",
                       "Dropped whatever their score: the community’s rules come first.", policy))
    if too_old:
        groups.append((f"Too old for the daily queue ({len(too_old)})",
                       "Only posts from the last 7 days qualify, or 14 days if the thread is still very active.", too_old))
    if cut:
        groups.append((f"Queue already full ({len(cut)})",
                       f"Only the top {target} candidates go to review in one run.", cut))
    if comments:
        min_score = _num(report.get("min_comment_score"), 15)
        groups.append((f"Comments that aren’t asking for help ({len(comments)})",
                       f"A comment becomes a lead only if it scores {min_score:.0f} or more on its own words.", comments))
    return groups


def guardrail_changes(raw: str, final: str) -> list[str]:
    """Describe what the reply sanitizer removed from the model's raw text."""
    changes = []
    for link in URL_RE.findall(raw):
        if link.rstrip(".,;:)!") not in final:
            changes.append(f"removed the link <code>{esc(link.rstrip('.,;:)!'))}</code>")
    for sentence in re.split(r"(?<=[.!?])\s+", raw.strip()):
        if sentence and not URL_RE.search(sentence) and sentence.strip() not in final:
            changes.append(f"removed “{esc(sentence.strip())}”")
    return changes


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


def render_card(lead: dict, index: int, recorded: dict) -> str:
    source = lead.get("source", "reddit")
    lead_type = lead.get("lead_type", "post")
    if source == "x":
        where, who, kind = "X", f"@{lead.get('author', '')}", "Post"
    else:
        where, kind = f"r/{lead.get('subreddit', '')}", "Comment" if lead_type == "comment" else "Post"
        who = f"u/{lead.get('reddit_username') or lead.get('author', '')}"
    if (lead.get("promo_mode") or lead.get("subreddit_policy_mode")) == "link_allowed":
        policy = '<span class="tag tag-link">Link allowed</span>'
    else:
        policy = '<span class="tag tag-mention">Mention only, no link</span>'

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
        sources = f'<p class="note">Facts pulled only from: {links}</p>'

    final = lead.get("reply") or ""
    entry = recorded.get(lead.get("url") or "")
    if entry and entry.get("raw"):
        label = f"Drafted reply · written by {esc(entry.get('model'))} running locally, not edited"
        changes = guardrail_changes(entry["raw"], final)
        guard = (
            f'<p class="guard">Guardrail: {"; ".join(changes)}.</p>' if changes
            else '<p class="note">Guardrail: nothing needed removing.</p>'
        )
        reply_html = esc(final)
    else:
        label = "Drafted reply · placeholder from the stand-in model"
        guard = ""
        reply_html = esc(final).replace(esc(PLACEHOLDER), f'<span class="placeholder">{esc(PLACEHOLDER)}</span>')

    score = lead["lead_score"]
    band = "high" if score >= 70 else "mid" if score >= 50 else "low"
    return f"""
    <article class="card" id="lead-{index}" data-state="waiting">
      <div class="card-head">
        <div class="score score-{band}" aria-label="Lead score {score:.1f} out of 100">{score:.1f}</div>
        <div class="card-title">
          <h3>{esc(lead.get('title'))}</h3>
          <p class="meta">{esc(kind)} · {esc(where)} · {esc(who)} · {esc(age_text(lead['breakdown'].get('age_hours')))} when scored {policy}</p>
        </div>
      </div>
      {original}
      <details>
        <summary>Score breakdown</summary>
        {render_breakdown(lead)}
      </details>
      <div class="reply">
        <p class="reply-label">{label}</p>
        <p>{reply_html}</p>
        {guard}
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
code { font-size: 13px; background: #eaeef2; border-radius: 4px; padding: 1px 5px; }
.wrap { max-width: 980px; margin: 0 auto; padding: 32px 20px 56px; }
header h1 { font-size: 30px; line-height:1.2; margin: 0 0 8px; }
.lede { font-size: 18px; margin: 0 0 10px; }
.byline, .muted, .note { color: var(--muted); }
.byline { margin: 0 0 14px; }
.notice { background: var(--warn-soft); border:1px solid #d4a72c55; border-radius: 8px; padding: 10px 14px; font-size: 14px; }
.notice p { margin: 0; }
.notice p + p { margin-top: 6px; }
h2 { font-size: 20px; margin: 36px 0 12px; }
.tiles { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; }
.tile { background: var(--card); border:1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.tile .num { font-size: 30px; font-weight: 650; line-height: 1.1; font-variant-numeric: tabular-nums; }
.tile .label { color: var(--muted); font-size: 14px; }
.panel { background: var(--card); border:1px solid var(--line); border-radius: 10px; padding: 6px 18px 10px; }
.panel h3 { font-size: 16px; margin: 12px 0 2px; }
.panel .why { margin: 0 0 6px; font-size: 14px; color: var(--muted); }
.panel ul { margin: 4px 0 8px; padding-left: 22px; }
.panel li { margin: 4px 0; }
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
.guard { font-size: 14px; margin: 8px 0 0; color: #0a3069; }
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


def build_page(leads: list[dict], report: dict, recordings: dict) -> str:
    recorded = recordings.get("replies", {})
    models = sorted({entry.get("model") for entry in recorded.values() if entry.get("model")})
    has_recordings = any((lead.get("url") or "") in recorded for lead in leads)
    used, rejected = grounding_summary(leads)
    link_removed = sum(
        1 for lead in leads if lead.get("promo_mode") == "mention_only" and "joinaila.com" not in (lead.get("reply") or "")
    )
    link_kept = sum(
        1 for lead in leads if lead.get("promo_mode") == "link_allowed" and "joinaila.com" in (lead.get("reply") or "")
    )
    candidates = report.get("candidates", [])
    turned_down = sum(1 for c in candidates if not c["kept"])
    scored = len(candidates) or len(leads)
    groups = said_no_groups(report)
    rejected_text = " and ".join(f"<strong>{esc(d)}</strong> ({esc(r)})" for d, r in rejected)
    used_text = " and ".join(f"<strong>{esc(d)}</strong>" for d in used)
    cards = "".join(render_card(lead, i + 1, recorded) for i, lead in enumerate(leads))

    if has_recordings:
        model_text = " and ".join(esc(m) for m in models) or "a local model"
        replies_note = (
            f"The replies were written by {model_text} running locally through Ollama, using the agent’s real prompts, "
            f"on {esc(recordings.get('recorded_on', ''))}. They are not edited; any changes come from the agent’s own guardrails."
        )
    else:
        replies_note = "The language model is replaced by a stand-in here, so the replies are placeholders."

    said_no = ""
    if groups:
        said_no = '<h2>What it said no to</h2><div class="panel">' + "".join(
            f"<h3>{title}</h3><p class='why'>{why}</p><ul>{''.join(f'<li>{item}</li>' for item in items)}</ul>"
            for title, why, items in groups
        ) + "</div>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aila Waitlist Agent — interactive demo</title>
<meta name="description" content="Finds people asking for help with trip planning on Reddit and X, scores each post 0–100 and drafts a reply that a person approves before anything is posted.">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Aila Waitlist Agent — interactive demo</h1>
  <p class="lede">Finds people asking for help with trip planning on Reddit and X, scores each post 0–100, and drafts a reply
  that a person approves before anything is posted.</p>
  <p class="byline">Built by Unmesh Achar during his internship at Lunar Guide (Feb–Jun 2026) to grow the waitlist for Aila,
  its AI travel planner · <a href="{REPO_URL}">Code on GitHub</a></p>
  <div class="notice">
    <p>This page is the agent’s real code run on <strong>made-up sample posts</strong> (not real people), with
    <code>run_pipeline.py --demo</code>. {replies_note}</p>
    <p>Not shown here: collecting live posts from Reddit and X, the scheduled daily run, and saving review decisions.
    Those need the full app. The buttons below only change this page.</p>
  </div>
</header>

<h2>This run at a glance</h2>
<div class="tiles">
  <div class="tile"><div class="num">{scored}</div><div class="label">candidates scored</div></div>
  <div class="tile"><div class="num">{turned_down}</div><div class="label">turned down</div></div>
  <div class="tile"><div class="num">{len(leads)}</div><div class="label">in the review queue</div></div>
  <div class="tile"><div class="num">0</div><div class="label">posted automatically</div></div>
</div>

{said_no}

<h2>Guardrails on the replies</h2>
<ul class="guards">
  <li><strong>Official sources only</strong> for facts: replies use {used_text}. The search also returned {rejected_text}, and the allowlist rejected them.</li>
  <li><strong>No link where it isn’t allowed:</strong> {link_removed} replies are in communities that allow a mention of Aila but not a link, so they carry no link; {link_kept} replies on X include it.</li>
  <li><strong>Nothing is posted automatically.</strong> Every reply waits for a person to approve or reject it.</li>
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
  <li>Pull any facts (visa, airline rules) only from an allowlist of official domains.</li>
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
    parser.add_argument("--report", default=None, help="run report (default: next to the database)")
    parser.add_argument("--out", default="site", help="output folder")
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        sys.exit(f"{db} not found: run `python3 run_pipeline.py --demo` first")
    report_path = Path(args.report) if args.report else (
        ROOT / RUN_REPORT if db.resolve() == (ROOT / DEMO_DATABASE).resolve() else db.parent / Path(RUN_REPORT).name
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    page = build_page(load_leads(db), load_report(report_path), load_recorded_replies())
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Wrote {out / 'index.html'}")


if __name__ == "__main__":
    main()

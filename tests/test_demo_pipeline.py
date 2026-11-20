"""End to end: the CLI's offline demo runs the real pipeline and stores sensible leads."""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_demo_run_end_to_end(demo_run):
    _, demo_db = demo_run
    con = sqlite3.connect(demo_db)
    con.row_factory = sqlite3.Row
    leads = [dict(row) for row in con.execute("SELECT * FROM leads")]
    con.close()

    assert leads, "the demo should store leads"
    # Communities whose rules don't allow promotion never reach the queue.
    assert not {lead["subreddit"] for lead in leads} & {"travel", "solotravel"}
    # Both sources and comment-based leads come through.
    assert {lead["source"] for lead in leads} == {"reddit", "x"}
    assert any(lead["lead_type"] == "comment" for lead in leads)
    recorded = json.loads((ROOT / "demo" / "fixtures" / "recorded_replies.json").read_text(encoding="utf-8"))["replies"]
    for lead in leads:
        # Each reply is the recorded model output after the guardrails, never the placeholder.
        assert lead["url"] in recorded
        assert lead["reply"] and not lead["reply"].startswith("[Demo reply")
        if lead["subreddit_policy_mode"] == "mention_only":
            assert "joinaila.com" not in lead["reply"]
        for source in json.loads(lead["reply_sources"] or "[]"):
            assert source["domain"] in {"travel.state.gov", "europa.eu"}


def test_run_report_explains_every_candidate(demo_run):
    _, demo_db = demo_run
    report = json.loads((demo_db.parent / "run_report.json").read_text(encoding="utf-8"))
    turned_down = [c for c in report["candidates"] if not c["kept"]]
    assert sorted(c["subreddit"] for c in turned_down if c["promo_mode"] == "disallowed_or_unclear") == [
        "backpacking", "solotravel", "travel"
    ]
    assert sorted(round(c["age_hours"] / 24) for c in turned_down if c["recency_bucket"] == 4) == [10, 20]
    assert len(turned_down) == 5
    assert sum(1 for c in report["comments"] if not c["became_lead"]) == 2
    with sqlite3.connect(demo_db) as con:
        assert con.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == sum(c["kept"] for c in report["candidates"])


def test_only_the_europe_question_gets_official_sources(demo_run):
    _, demo_db = demo_run
    with sqlite3.connect(demo_db) as con:
        rows = con.execute("SELECT title, reply_sources FROM leads").fetchall()
    grounded = {title for title, sources in rows if json.loads(sources or "[]")}
    assert grounded == {"Do I need a visa for a Schengen stopover as a US citizen?"}

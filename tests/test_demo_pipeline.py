"""End to end: the CLI's offline demo runs the real pipeline and stores sensible leads."""

import json
import sqlite3


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
    for lead in leads:
        assert lead["reply"].startswith("[Demo reply")
        if lead["subreddit_policy_mode"] == "mention_only":
            assert "joinaila.com" not in lead["reply"]
        for source in json.loads(lead["reply_sources"] or "[]"):
            assert source["domain"] in {"travel.state.gov", "europa.eu"}

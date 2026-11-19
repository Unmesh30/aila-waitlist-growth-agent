"""The review dashboard renders the demo leads, and approving one updates the database."""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

ROOT = Path(__file__).resolve().parent.parent

# Run in a fresh interpreter so the app reads DATABASE_PATH from the environment.
SCRIPT = textwrap.dedent(
    """
    import json
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("app/streamlit_app.py", default_timeout=60)
    at.run()
    before = {
        "exceptions": [str(e.value) for e in at.exception],
        "headers": [h.value for h in at.header],
        "approve_buttons": sum("Approve" in b.label for b in at.button),
    }
    next(b for b in at.button if "Approve" in b.label).click().run()
    after = {"exceptions": [str(e.value) for e in at.exception], "headers": [h.value for h in at.header]}
    print("RESULT " + json.dumps({"before": before, "after": after}))
    """
)


def test_dashboard_renders_leads_and_records_an_approval(demo_run, tmp_path):
    _, demo_db = demo_run
    db = tmp_path / "dashboard.db"
    shutil.copy(demo_db, db)
    with sqlite3.connect(db) as con:
        total = con.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

    env = {**os.environ, "DATABASE_PATH": str(db)}
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    line = next(text for text in result.stdout.splitlines() if text.startswith("RESULT "))
    report = json.loads(line[len("RESULT "):])

    assert report["before"]["exceptions"] == []
    assert report["before"]["headers"] == [f"New Leads ({total})"]
    assert report["before"]["approve_buttons"] == total
    assert report["after"]["exceptions"] == []
    assert report["after"]["headers"] == [f"New Leads ({total - 1})"]

    with sqlite3.connect(db) as con:
        statuses = dict(con.execute("SELECT status, COUNT(*) FROM leads GROUP BY status").fetchall())
    assert statuses == {"approved": 1, "new": total - 1}

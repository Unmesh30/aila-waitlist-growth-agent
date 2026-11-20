"""The live-demo page is built from the demo run and shows what the guardrails did."""

import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_export_site_from_demo_run(demo_run, tmp_path):
    _, demo_db = demo_run
    result = subprocess.run(
        [sys.executable, "-m", "demo.export_site", "--db", str(demo_db), "--out", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert (tmp_path / ".nojekyll").exists()

    with sqlite3.connect(demo_db) as con:
        queued = con.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    assert page.count('<article class="card"') == queued
    assert "made-up sample posts" in page
    # What the run turned down is listed with the reason: community rules, age and comments that aren't leads.
    assert "Communities that don’t allow promotion (3)" in page
    assert "Too old for the daily queue (2)" in page
    assert "Comments that aren’t asking for help (2)" in page
    for community in ("r/travel", "r/solotravel", "r/backpacking"):
        assert f"({community} · score" in page
    # The look-alike domain is shown as rejected; replies cite only official sources.
    assert "visa-help-gov.uk</strong> (look-alike" in page
    # Mention-only cards never carry the waitlist link.
    for card in re.findall(r'<article class="card".*?</article>', page, flags=re.S):
        if "Mention only" in card:
            assert "joinaila.com" not in card

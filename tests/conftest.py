"""Test setup: an isolated database and log file, and no network access."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="aila-tests-")
os.environ["DATABASE_PATH"] = os.path.join(_TMP, "test_leads.db")
os.environ["LOG_FILE"] = os.path.join(_TMP, "test.log")
os.environ["TEST_MODE"] = "true"
os.environ["AILA_ALLOW_DB_RESET"] = "1"
os.environ["X_DELAY_BETWEEN_GENERATIONS"] = "0"
os.environ["X_BEARER_TOKEN"] = ""

DEMO_DB = ROOT / "data" / "demo" / "demo_leads.db"


@pytest.fixture(scope="session")
def demo_run():
    """Run the CLI's offline demo once (`python run_pipeline.py --demo`) and share the result."""
    result = subprocess.run(
        [sys.executable, "run_pipeline.py", "--demo"], cwd=ROOT, capture_output=True, text=True, timeout=180
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result, DEMO_DB

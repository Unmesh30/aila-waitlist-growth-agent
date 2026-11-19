"""Offline demo mode: runs the real pipeline on bundled sample data.

`python3 run_pipeline.py --demo` never contacts Reddit, X, a search engine or Ollama:

* the Reddit and X collectors return the anonymised sample posts in demo/fixtures/
* comment enrichment attaches the sample comments in demo/fixtures/comments.json
* source grounding gets fixed search results (one blog, one look-alike domain and two
  official pages), so the real allowlist decides which sources a reply may use
* a stub model returns the same clearly labelled placeholder reply every time

Scoring, ranking, the per-community promotion policy, the reply sanitizer and storage
are the project's real code. Demo leads go to their own database, data/demo/demo_leads.db.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEMO_DATABASE = "data/demo/demo_leads.db"
DEMO_LOG = "logs/demo.log"

DEMO_REPLY = (
    "[Demo reply: placeholder text, not written by a model] "
    "That planning overload is really common. What helps most is keeping flights, stays and the "
    "day-by-day plan in one place, and checking entry rules on the official government site. "
    "We're building Aila, an all-in-one travel planner, for exactly this: https://joinaila.com/"
)


def configure_env() -> None:
    """Point the app at the demo database. Must run before config.settings is imported."""
    os.environ["DATABASE_PATH"] = DEMO_DATABASE
    os.environ["LOG_FILE"] = DEMO_LOG
    os.environ["TEST_MODE"] = "true"
    os.environ["ENABLE_REPLY_GROUNDING"] = "true"
    os.environ["X_DELAY_BETWEEN_GENERATIONS"] = "0"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _fresh(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Copy fixture items, turning each age_hours into a created_utc relative to now."""
    now = time.time()
    fresh = []
    for item in items:
        item = dict(item)
        item["created_utc"] = now - float(item.pop("age_hours", 6)) * 3600
        fresh.append(item)
    return fresh


def demo_collect_recent_discussions(*args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
    return _fresh(_load("reddit_posts.json"))


def demo_collect_recent_tweets(*args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
    return _fresh(_load("x_tweets.json"))


def demo_enrich_posts_with_comments(
    posts: List[Dict[str, Any]], max_posts_to_enrich: int = 30, **kwargs: Any
) -> List[Dict[str, Any]]:
    comments = _load("comments.json")
    enriched = []
    for post in posts[:max_posts_to_enrich]:
        post = dict(post)
        post["top_comments"] = _fresh(comments.get(post.get("url"), []))
        enriched.append(post)
    return enriched


def demo_search(query: str):
    return [tuple(result) for result in _load("search_results.json")]


def demo_fetch_snippet(url: str) -> str:
    return f"[Demo source] In a real run this is the opening text fetched from {url}"


class DemoLLMClient:
    """Stands in for OllamaClient: same interface, no network, fixed labelled output."""

    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = "demo"
        self.model = model or "demo-stub"

    def check_connection(self) -> bool:
        return True

    def generate(self, prompt: str, system: str | None = None, temperature: float = 0.7,
                 max_tokens: int = 300) -> str:
        return DEMO_REPLY


def install_stubs() -> None:
    """Swap the network-facing pieces for the offline ones above."""
    from src.collectors import comment_extractor
    from src.llm import reply_generator, source_grounder
    from src.pipeline import discovery_pipeline, drafting_pipeline

    discovery_pipeline.collect_recent_discussions = demo_collect_recent_discussions
    discovery_pipeline.collect_recent_tweets = demo_collect_recent_tweets
    discovery_pipeline.enrich_posts_with_comments = demo_enrich_posts_with_comments
    comment_extractor.enrich_posts_with_comments = demo_enrich_posts_with_comments
    source_grounder._search_duckduckgo = demo_search
    source_grounder._fetch_snippet = demo_fetch_snippet
    reply_generator.OllamaClient = DemoLLMClient
    drafting_pipeline.test_ollama_connection = lambda: True


def reset_database() -> None:
    """Start every demo run from an empty demo database, so the dedup step keeps the samples.

    Only ever deletes the demo database (or a test database when AILA_ALLOW_DB_RESET=1).
    """
    from config.settings import DATABASE_PATH, PROJECT_ROOT

    db = Path(DATABASE_PATH).resolve()
    is_demo_db = db == (PROJECT_ROOT / DEMO_DATABASE).resolve()
    if db.exists() and (is_demo_db or os.environ.get("AILA_ALLOW_DB_RESET") == "1"):
        db.unlink()

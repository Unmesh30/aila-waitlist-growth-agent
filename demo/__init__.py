"""Offline demo mode: runs the real pipeline on bundled, made-up sample posts.

`python3 run_pipeline.py --demo` never contacts Reddit, X, a search engine or Ollama:

* the Reddit and X collectors return the made-up sample posts in demo/fixtures/
* comment enrichment attaches the sample comments in demo/fixtures/comments.json
* source grounding gets fixed search results (one blog, one look-alike domain and two
  official pages), so the real allowlist decides which sources a reply may use
* the model is replaced by a stand-in. It replays the raw replies recorded from a real
  local model in demo/fixtures/recorded_replies.json, or returns a labelled placeholder
  when there is no recording for a lead

`python3 run_pipeline.py --demo --record-replies` is the same run with the real model
(Ollama) switched back on. It saves each raw model reply to demo/fixtures/recorded_replies.json.

Scoring, ranking, the per-community promotion policy, the reply sanitizer and storage
are the project's real code. Demo leads go to their own database, data/demo/demo_leads.db,
and data/demo/run_report.json records every candidate and what happened to it.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
RECORDED_REPLIES = FIXTURES / "recorded_replies.json"
DEMO_DATABASE = "data/demo/demo_leads.db"
RUN_REPORT = "data/demo/run_report.json"
DEMO_LOG = "logs/demo.log"

DEMO_REPLY = (
    "[Demo reply: placeholder text, not written by a model] "
    "That planning overload is really common. What helps most is keeping flights, stays and the "
    "day-by-day plan in one place, and checking entry rules on the official government site. "
    "We're building Aila, an all-in-one travel planner, for exactly this: https://joinaila.com/"
)

# The lead whose reply is being generated, so recorded replies can be saved and replayed per lead.
_current_lead: Dict[str, Any] = {"url": None}
_report: Dict[str, Any] = {}


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
    return _load("snippets.json").get(url, "")


def recorded_replies_path() -> Path:
    return Path(os.environ.get("AILA_DEMO_REPLIES") or RECORDED_REPLIES)


def load_recorded_replies() -> Dict[str, Any]:
    path = recorded_replies_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class DemoLLMClient:
    """Stands in for OllamaClient: same interface, no network.

    Returns the recorded real-model reply for the current lead, or the labelled placeholder.
    """

    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = "demo"
        self.model = model or "demo-stub"

    def check_connection(self) -> bool:
        return True

    def generate(self, prompt: str, system: str | None = None, temperature: float = 0.7,
                 max_tokens: int = 300) -> str:
        entry = load_recorded_replies().get("replies", {}).get(_current_lead["url"] or "")
        return entry["raw"] if entry and entry.get("raw") else DEMO_REPLY


def _track_current_lead() -> None:
    from src.llm.reply_generator import ReplyGenerator

    original = ReplyGenerator.generate_reply
    if getattr(original, "_demo_wrapped", False):
        return

    def generate_reply(self, lead):
        _current_lead["url"] = lead.get("url")
        try:
            return original(self, lead)
        finally:
            _current_lead["url"] = None

    generate_reply._demo_wrapped = True
    ReplyGenerator.generate_reply = generate_reply


def _install_recorder() -> None:
    """Keep the real Ollama client, and save each raw reply it returns for the current lead."""
    from src.llm.ollama_client import OllamaClient

    original = OllamaClient.generate
    path = recorded_replies_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "note": (
            "Raw replies from a local model (Ollama) for the made-up sample posts, recorded with "
            "`python3 run_pipeline.py --demo --record-replies` and not edited. `--demo` replays them; "
            "the reply sanitizer still runs on every one."
        ),
        "recorded_on": date.today().isoformat(),
        "replies": {},
    }

    def save() -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def generate(self, prompt, system=None, temperature=0.7, max_tokens=300):
        raw = original(self, prompt, system=system, temperature=temperature, max_tokens=max_tokens)
        url = _current_lead["url"]
        if raw and url:
            data["replies"][url] = {"model": self.model, "raw": raw}
            save()
        return raw

    OllamaClient.generate = generate


def _install_run_report() -> None:
    """Record every candidate the run considered and whether it reached the review queue."""
    from config import settings
    from src.pipeline import discovery_pipeline
    from src.scoring import ranker
    from src.scoring.lead_scorer import score_comment_as_lead

    original_extract = discovery_pipeline.extract_comment_leads
    original_rank = discovery_pipeline.rank_leads

    def extract_comment_leads(posts, *args, **kwargs):
        leads = original_extract(posts, *args, **kwargs)
        became_leads = {lead.get("comment_text") for lead in leads}
        rows = []
        for post in posts:
            context = f"{post.get('title', '')} {post.get('selftext', '')}"
            for comment in post.get("top_comments", []):
                body = comment.get("body", "")
                score, _ = score_comment_as_lead(body, context)
                rows.append({
                    "post_title": post.get("title"),
                    "subreddit": post.get("subreddit"),
                    "author": comment.get("author"),
                    "body": body,
                    "score": round(float(score), 1),
                    "became_lead": body in became_leads,
                })
        _report["comments"] = rows
        _report["min_comment_score"] = kwargs.get("min_comment_score", args[0] if args else 15.0)
        return leads

    def rank_leads(scored, *args, **kwargs):
        kept = original_rank(scored, *args, **kwargs)
        kept_urls = {lead.get("url") for lead in kept}
        _report["target_final_leads"] = settings.TARGET_FINAL_LEADS
        _report["candidates"] = [
            {
                "url": lead.get("url"),
                "title": lead.get("title"),
                "subreddit": lead.get("subreddit"),
                "source": lead.get("source", "reddit"),
                "lead_type": lead.get("lead_type", "post"),
                "comment_text": lead.get("comment_text"),
                "lead_score": round(float(lead.get("lead_score", 0)), 2),
                "age_hours": round(float(ranker._get_age_hours(lead) or 0), 1),
                "promo_mode": lead.get("promo_mode"),
                "recency_bucket": ranker._recency_bucket(lead),
                "kept": lead.get("url") in kept_urls,
            }
            for lead in scored
        ]
        report_path = ROOT / RUN_REPORT
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return kept

    discovery_pipeline.extract_comment_leads = extract_comment_leads
    discovery_pipeline.rank_leads = rank_leads


def install_stubs(record_replies: bool = False) -> None:
    """Swap the network-facing pieces for the offline ones above.

    With record_replies=True the real model stays on and its raw replies are saved.
    """
    from src.collectors import comment_extractor
    from src.llm import reply_generator, source_grounder
    from src.pipeline import discovery_pipeline, drafting_pipeline

    discovery_pipeline.collect_recent_discussions = demo_collect_recent_discussions
    discovery_pipeline.collect_recent_tweets = demo_collect_recent_tweets
    discovery_pipeline.enrich_posts_with_comments = demo_enrich_posts_with_comments
    comment_extractor.enrich_posts_with_comments = demo_enrich_posts_with_comments
    source_grounder._search_duckduckgo = demo_search
    source_grounder._fetch_snippet = demo_fetch_snippet
    _track_current_lead()
    _install_run_report()
    if record_replies:
        _install_recorder()
    else:
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

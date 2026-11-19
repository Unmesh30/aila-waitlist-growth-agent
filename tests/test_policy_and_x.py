import time

from config.sources import get_promo_mode
from src.collectors.x_collector import _normalize_tweet
from src.scoring.ranker import rank_leads


def test_promotion_policy_per_community():
    assert get_promo_mode("travel") == "disallowed_or_unclear"
    assert get_promo_mode("digitalnomad") == "mention_only"
    assert get_promo_mode("SideProject") == "link_allowed"
    assert get_promo_mode("some_unknown_subreddit") == "disallowed_or_unclear"
    assert get_promo_mode("anything", source="x") == "link_allowed"


def test_ranking_never_queues_communities_that_disallow_promotion():
    now = time.time()
    leads = [
        {"url": f"https://example.org/{name}", "subreddit": name, "source": "reddit", "lead_score": 80,
         "created_utc": now - 3600, "num_comments": 10, "score": 20, "score_breakdown": {"age_hours": 1.0}}
        for name in ("travel", "solotravel", "digitalnomad", "studyAbroad")
    ]
    kept = {lead["subreddit"] for lead in rank_leads(leads)}
    assert kept == {"digitalnomad", "studyAbroad"}


def test_x_api_tweet_is_normalised_into_a_lead():
    tweet = {
        "id": "123",
        "author_id": "u1",
        "text": "any travel app recommendation for planning a trip?",
        "created_at": "2026-11-19T10:00:00.000Z",
        "public_metrics": {"like_count": 5, "reply_count": 2},
    }
    lead = _normalize_tweet(tweet, {"u1": {"username": "someone"}})
    assert lead["url"] == "https://x.com/someone/status/123"
    assert lead["source"] == "x" and lead["lead_type"] == "tweet"
    assert lead["engagement_score"] == 7


def test_tweet_without_a_username_is_skipped():
    tweet = {"id": "1", "author_id": "missing", "text": "help planning a trip"}
    assert _normalize_tweet(tweet, {}) is None

import time

from config.scoring import SCORING_WEIGHTS
from src.scoring.lead_scorer import calculate_lead_score


def _post(title, text, hours_old=2, score=30, comments=12, subreddit="digitalnomad"):
    return {
        "title": title,
        "selftext": text,
        "subreddit": subreddit,
        "source": "reddit",
        "score": score,
        "num_comments": comments,
        "created_utc": time.time() - hours_old * 3600,
        "url": f"https://example.org/{abs(hash(title))}",
    }


def test_weights_match_the_documented_split():
    assert SCORING_WEIGHTS == {
        "pain_points": 0.30,
        "request": 0.25,
        "engagement": 0.20,
        "recency": 0.15,
        "quality": 0.10,
    }
    assert abs(sum(SCORING_WEIGHTS.values()) - 1.0) < 1e-9


def test_a_fresh_travel_planning_request_beats_an_off_topic_post():
    strong = calculate_lead_score(_post(
        "Overwhelmed planning a 3-week trip: any app recommendation for the itinerary?",
        "Flights, hotels and the itinerary are spread across five apps and I'm stressed. Can anyone recommend one app?",
    ))
    off_topic = calculate_lead_score(_post(
        "What keyboard do you use?", "Looking for a mechanical keyboard for coding.",
    ))
    assert strong["total_score"] > off_topic["total_score"]
    for result in (strong, off_topic):
        assert 0 <= result["total_score"] <= 100


def test_an_older_post_scores_lower_than_the_same_post_today():
    title = "Need help planning my trip itinerary, any travel app recommendation?"
    text = "Planning a trip to Japan and I'm overwhelmed. Can anyone recommend a planning app?"
    today = calculate_lead_score(_post(title, text, hours_old=2))
    last_month = calculate_lead_score(_post(title, text, hours_old=24 * 25))
    assert today["total_score"] > last_month["total_score"]

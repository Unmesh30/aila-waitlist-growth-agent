"""Configuration for X (Twitter) discovery and reply generation."""

import os

X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", os.getenv("TWITTER_BEARER_TOKEN", ""))
ENABLE_X_COLLECTION = os.getenv("ENABLE_X_COLLECTION", "true").lower() == "true"

X_SEARCH_QUERIES = [
    "travel planning help",
    "trip planning is stressful",
    "any travel app recommendation",
    "how do you plan trips",
    "itinerary help",
    "cheap flights tips",
    "solo travel advice",
    "best travel tools",
]

X_ENGAGEMENT_THRESHOLD = int(os.getenv("X_ENGAGEMENT_THRESHOLD", "1"))
X_RECENCY_WINDOW_HOURS = int(os.getenv("X_RECENCY_WINDOW_HOURS", "48"))
X_MAX_COLLECTION_LIMIT = int(os.getenv("X_MAX_COLLECTION_LIMIT", "80"))
X_MAX_RESULTS_PER_QUERY = int(os.getenv("X_MAX_RESULTS_PER_QUERY", "20"))

X_MAX_TWEETS_PER_RUN = int(os.getenv("X_MAX_TWEETS_PER_RUN", "80"))
X_MAX_REPLIES_GENERATED = int(os.getenv("X_MAX_REPLIES_GENERATED", "40"))
X_DELAY_BETWEEN_GENERATIONS = float(os.getenv("X_DELAY_BETWEEN_GENERATIONS", "0.2"))
X_MAX_REPLIES_PER_USER = int(os.getenv("X_MAX_REPLIES_PER_USER", "1"))

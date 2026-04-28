"""Global settings for Aila Waitlist Agent."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Ollama settings
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")  # Default model for grounded reply generation
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT = 120  # seconds

# Reply grounding settings
ENABLE_REPLY_GROUNDING = os.getenv("ENABLE_REPLY_GROUNDING", "true").lower() == "true"
GROUNDING_TIMEOUT = int(os.getenv("GROUNDING_TIMEOUT", "12"))
GROUNDING_MAX_SOURCES = int(os.getenv("GROUNDING_MAX_SOURCES", "3"))

# Reddit settings
REDDIT_USER_AGENT = os.getenv(
    "REDDIT_USER_AGENT",
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36 "
        "AilaWaitlistAgent/1.0 (travel app lead finder; contact: hello@aila.travel)"
    )
)
REDDIT_SEARCH_LIMIT = int(os.getenv("REDDIT_SEARCH_LIMIT", "50"))
REDDIT_SUBREDDIT_LIMIT = int(os.getenv("REDDIT_SUBREDDIT_LIMIT", "25"))
REDDIT_TIMEOUT = 15  # seconds

# Temporary controlled validation mode
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

# Overnight run targets
TARGET_FINAL_LEADS = int(os.getenv("TARGET_FINAL_LEADS", "15" if TEST_MODE else "250"))
TARGET_CANDIDATE_POOL = int(os.getenv("TARGET_CANDIDATE_POOL", "60" if TEST_MODE else "450"))
MAX_COLLECTION_PASSES = int(os.getenv("MAX_COLLECTION_PASSES", "1" if TEST_MODE else "3"))
MAX_OLDER_EXCEPTIONAL_LEADS = int(os.getenv("MAX_OLDER_EXCEPTIONAL_LEADS", "2" if TEST_MODE else "20"))
DEFAULT_MAX_POSTS_TO_ENRICH = int(os.getenv("DEFAULT_MAX_POSTS_TO_ENRICH", "25" if TEST_MODE else "180"))
DEFAULT_TOP_COMMENTS_PER_POST = int(os.getenv("DEFAULT_TOP_COMMENTS_PER_POST", "5" if TEST_MODE else "12"))
REPLY_BATCH_SIZE = int(os.getenv("REPLY_BATCH_SIZE", "5" if TEST_MODE else "25"))
REVIEW_QUEUE_LIMIT = int(os.getenv("REVIEW_QUEUE_LIMIT", "300"))

# Reddit-safe outreach caps
MAX_PROMOTIONAL_MENTIONS_PER_RUN = int(os.getenv("MAX_PROMOTIONAL_MENTIONS_PER_RUN", "80"))
MAX_LINKED_REPLIES_PER_RUN = int(os.getenv("MAX_LINKED_REPLIES_PER_RUN", "25"))
MAX_PROMO_REPLIES_PER_SUBREDDIT_PER_RUN = int(os.getenv("MAX_PROMO_REPLIES_PER_SUBREDDIT_PER_RUN", "4"))

# Scoring settings - Dynamic top-N selection
MIN_LEAD_SCORE = int(os.getenv("MIN_LEAD_SCORE", "5"))  # Soft threshold (older behavior)
MIN_LEADS_TO_KEEP = int(os.getenv("MIN_LEADS_TO_KEEP", str(TARGET_FINAL_LEADS)))  # Always keep at least this many when possible
MAX_LEADS_TO_KEEP = int(os.getenv("MAX_LEADS_TO_KEEP", str(TARGET_FINAL_LEADS)))  # Cap at overnight target
# Legacy - kept for backwards compatibility
TOP_LEADS_LIMIT = MAX_LEADS_TO_KEEP

# Reply generation settings
MAX_LEADS_TO_DRAFT = int(os.getenv("MAX_LEADS_TO_DRAFT", str(TARGET_FINAL_LEADS)))  # How many leads to generate replies for

# Database settings
DATABASE_PATH = PROJECT_ROOT / os.getenv("DATABASE_PATH", "data/waitlist_leads.db")

# Logging settings
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = PROJECT_ROOT / os.getenv("LOG_FILE", "logs/pipeline.log")

# Aila product information
AILA_NAME = "Aila"
AILA_WAITLIST_URL = "https://joinaila.com/"
AILA_DESCRIPTION = "AI all-in-one travel app for planning, booking, itinerary organization, and real-time travel help"

# Date range for discovery (days back)
DISCOVERY_DAYS_BACK = int(os.getenv("DISCOVERY_DAYS_BACK", "30"))

"""Source configuration for content discovery."""

# Travel-related subreddits (high priority)
TRAVEL_SUBREDDITS = [
    "travel",
    "solotravel",
    "TravelHacks",
    "digitalnomad",
    "Shoestring",
    "TravelNoPics",
    "backpacking",
    "onebag",
    "NeedTravelAdvice",
    "awardtravel",
    "Flights",
    "roadtrip",
    "studyAbroad",
    "expats",
    "AskReddit",  # Generic but high volume
    "LifeProTips",
    "productivity",
    # Explicitly allowed adjacent communities for early-adopter/tool discussions
    "Entrepreneur",
    "startups",
    "SideProject",
    "alphaandbetausers",
    "indiehackers",
    "SaaS",
    "smallbusiness",
    "ProductHunters",
    "roastmystartup",
]

# Subreddit quality tiers for scoring boosts/penalties
# High-quality travel subreddits get a +20 boost
HIGH_QUALITY_TRAVEL_SUBREDDITS = [
    "travel",
    "solotravel",
    "TravelHacks",
    "digitalnomad",
    "Shoestring",
    "TravelNoPics",
    "backpacking",
    "onebag",
    "NeedTravelAdvice",
    "awardtravel",
    "Flights",
    "roadtrip",
]

# Low-quality or irrelevant subreddits get a -30 penalty (or exclusion)
BLOCKED_SUBREDDITS = [
    "gaming",
    "Games",
    "BestofRedditorUpdates",
    "AmItheAsshole",
    "relationship_advice",
    "relationships",
    "tifu",
    "TrueOffMyChest",
    "confessions",
    "stories",
    "nosleep",
]

# Search queries for travel pain points
TRAVEL_PAIN_QUERIES = [
    "travel app recommendations",
    "travel planning stress",
    "itinerary organization",
    "travel booking help",
    "too many travel apps",
    "trip planning advice",
    "solo travel planning",
    "travel budget help",
    "travel itinerary app",
    "organize travel plans",
    "travel documents organization",
    "best travel planning tool",
    "travel help advice",
    "trip planning help",
    "flight rebook help",
    "travel documents help",
    "travel budget planning",
    "travel organization app",
    "solo trip help",
    "real time travel help",
]

# Time filter for Reddit search
# Options: hour, day, week, month, year, all
REDDIT_TIME_FILTER = "month"

# Sort order for Reddit search
# Options: relevance, hot, top, new, comments
REDDIT_SORT_ORDER = "relevance"

# Subreddit/community-level promotion policy modes.
# Unknown communities default to "disallowed_or_unclear".
#
# Modes:
# - link_allowed: Aila mention plus waitlist link allowed when relevant
# - mention_only: Aila mention allowed, but no direct link
# - disallowed_or_unclear: exclude from final actionable outreach queue
SUBREDDIT_PROMOTION_POLICIES = {
    # Travel communities default to exclusion unless promotion is configured as acceptable.
    "travel": "disallowed_or_unclear",
    "solotravel": "disallowed_or_unclear",
    "TravelHacks": "disallowed_or_unclear",
    "digitalnomad": "mention_only",
    "Shoestring": "disallowed_or_unclear",
    "TravelNoPics": "disallowed_or_unclear",
    "backpacking": "disallowed_or_unclear",
    "onebag": "disallowed_or_unclear",
    "NeedTravelAdvice": "disallowed_or_unclear",
    "awardtravel": "disallowed_or_unclear",
    "Flights": "disallowed_or_unclear",
    "roadtrip": "disallowed_or_unclear",
    "studyAbroad": "mention_only",
    "expats": "mention_only",
    "AskReddit": "disallowed_or_unclear",
    "LifeProTips": "disallowed_or_unclear",
    "productivity": "mention_only",

    # Explicitly configurable startup/builder communities.
    "Entrepreneur": "mention_only",
    "startups": "mention_only",
    "SideProject": "link_allowed",
    "alphaandbetausers": "link_allowed",
    "indiebiz": "mention_only",
    "indiehackers": "link_allowed",
    "SaaS": "mention_only",
    "smallbusiness": "mention_only",
    "ProductHunters": "link_allowed",
    "roastmystartup": "link_allowed",
}


def normalize_promo_mode(mode: str | None) -> str:
    """Normalize legacy and missing promotion policy values."""
    if mode == "disallow_promo":
        return "disallowed_or_unclear"
    if mode in {"link_allowed", "mention_only", "disallowed_or_unclear"}:
        return mode
    return "disallowed_or_unclear"


def get_promo_mode(subreddit: str, source: str = "reddit") -> str:
    """Return configured promotion mode for a lead source/community."""
    if source == "x":
        return "link_allowed"
    return normalize_promo_mode(SUBREDDIT_PROMOTION_POLICIES.get(subreddit))


def promotion_flags_for_mode(mode: str) -> dict:
    """Return dashboard/storage flags for a promotion mode."""
    normalized = normalize_promo_mode(mode)
    return {
        "promo_mode": normalized,
        "link_allowed": normalized == "link_allowed",
        "mention_allowed": normalized in {"link_allowed", "mention_only"},
        "actionable_for_promotion": normalized in {"link_allowed", "mention_only"},
    }

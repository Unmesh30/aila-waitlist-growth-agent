"""Scoring configuration for lead quality assessment."""

# Pain point keywords with weights
PAIN_POINT_KEYWORDS = {
    # High intent - explicit problems (travel-specific)
    "too many travel apps": 15,
    "too many apps": 10,
    "app overload": 12,
    "app fatigue": 12,

    # Travel-product intent (STRONGEST SIGNALS)
    "travel app": 12,
    "trip app": 12,
    "travel tool": 11,
    "planning app": 10,
    "itinerary app": 13,
    "travel planner": 11,

    # Travel planning pain points (high weight)
    "planning stress": 9,
    "trip planning": 8,
    "travel planning": 8,
    "plan my trip": 9,
    "itinerary": 10,
    "organize trip": 9,
    "organize travel": 9,
    "keep track": 7,

    # Booking problems (travel-specific)
    "booking": 7,
    "reservation": 6,
    "booking confusion": 10,
    "booking friction": 10,
    "travel booking": 9,

    # Budget concerns (travel context)
    "travel budget": 8,
    "trip budget": 8,
    "budget": 5,

    # Solo travel (high intent)
    "solo travel": 9,
    "traveling alone": 8,
    "solo trip": 8,
    "first time travel": 7,

    # Travel logistics (strong signals)
    "documents": 7,
    "visa": 6,
    "passport": 5,
    "travel documents": 9,

    # Generic pain (LOW WEIGHT - needs travel context)
    "overwhelmed": 4,
    "frustrated": 3,
    "difficult": 2,
    "hard to": 2,
    "struggle": 3,
    "confusing": 3,

    # Tool/app seeking (travel-focused)
    "travel recommendation": 8,
    "travel advice": 7,
    "what app": 9,
    "which app": 9,
    "best app": 8,
    "best tool": 8,
    "app for travel": 11,
    "tool for travel": 10,
}

# Travel context keywords (REQUIRED for relevance)
# Posts must have at least ONE of these to be considered travel-relevant
TRAVEL_CONTEXT_KEYWORDS = [
    "travel",
    "trip",
    "vacation",
    "itinerary",
    "flight",
    "hotel",
    "hostel",
    "booking",
    "destination",
    "backpack",
    "solo travel",
    "budget travel",
    "nomad",
    "visa",
    "passport",
    "abroad",
    "overseas",
    "international",
    "journey",
]

# Comment-level lead indicators (HIGH INTENT)
# These indicate a commenter is also experiencing the pain and could be a lead
COMMENT_LEAD_INDICATORS = {
    # Strong agreement/shared pain (exact and variations)
    "i have the same": 15,
    "i've got the same": 15,
    "same issue": 12,
    "same problem": 12,
    "same here": 10,
    "same thing": 10,
    "me too": 8,
    "i also": 10,
    "i'm also": 10,
    "i do this too": 10,
    "this is me": 9,
    "struggling with this": 11,
    "dealing with this": 10,

    # Seeking solutions
    "does anyone know": 14,
    "anyone know": 12,
    "anyone have": 11,
    "looking for": 10,
    "is there a": 11,
    "is there an app": 13,
    "wish there was": 13,
    "wish there were": 13,
    "need something": 10,
    "need an app": 12,
    "need a tool": 12,
    "better app": 12,
    "better tool": 12,
    "alternative": 9,
    "recommendations": 10,
    "any suggestions": 11,

    # App/tool fatigue
    "use multiple": 11,
    "using multiple": 11,
    "multiple apps": 11,
    "different apps": 10,
    "5 different apps": 14,
    "so many apps": 13,
    "too many apps": 14,
    "hate switching": 11,
    "switching between": 10,
    "juggling": 10,

    # Planning frustration
    "trip planning": 10,
    "travel planning": 10,
    "planning is": 9,
    "overwhelming": 9,
    "so confusing": 10,
    "confusing": 7,
    "hard to": 8,
    "difficult to": 8,
    "frustrated": 8,
    "pain": 7,

    # Request for help
    "recommend": 9,
    "recommendations": 10,
    "suggestions": 9,
    "what do you use": 12,
    "what do you": 10,
    "how do you": 10,
    "help me": 9,
    "any advice": 10,
    "following": 7,  # "following" often means interested

    # App seeking (direct)
    "app for": 11,
    "tool for": 11,
    "apps for": 11,
    "best app": 12,
    "good app": 11,
    "travel app": 12,
}

# Request indicators (explicit ask for help)
REQUEST_INDICATORS = [
    "recommend",
    "suggestion",
    "advice",
    "help",
    "what should",
    "how do i",
    "anyone know",
    "looking for",
    "need",
    "?",  # Question mark is a request indicator
]

# Quality indicators (longer, more specific posts)
QUALITY_INDICATORS = {
    "min_length": 50,  # Minimum character length for quality
    "has_question": 2,  # Bonus for having a question
    "has_details": 2,   # Bonus for detailed post
}

# Scoring weights
SCORING_WEIGHTS = {
    "pain_points": 0.30,      # Mentions travel pain points
    "request": 0.25,          # Explicit request for help
    "engagement": 0.20,       # Reddit upvotes/comments
    "recency": 0.15,          # How recent the post is
    "quality": 0.10,          # Post quality and specificity
}

# Recency decay (days -> score multiplier)
RECENCY_DECAY = {
    1: 1.0,    # Today
    3: 0.95,   # Last 3 days
    7: 0.85,   # Last week
    14: 0.70,  # Last 2 weeks
    30: 0.50,  # Last month
}

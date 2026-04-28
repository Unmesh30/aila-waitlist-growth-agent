# Aila Waitlist Agent

**Local-first lead discovery and reply generation for building Aila's waitlist.**

Automatically finds recent Reddit discussions from likely potential users, scores them by quality, and generates one personalized reply per selected lead using local Ollama (llama3).

## 🎯 What It Does

1. **Discovers** recent travel discussions on Reddit from people experiencing pain points Aila solves
2. **Scores** each post/comment by likelihood of being a good waitlist lead
3. **Generates** one final reply for top leads using local Ollama
4. **Saves** everything to a local SQLite database
5. **Provides** a Streamlit dashboard for manual review and approval

**Important:** This system is for manual review only. It does NOT auto-post. You review, approve, and manually post replies.

## 🏗️ Architecture

Built with **local-first** principles:
- ✅ **No paid APIs required** for core workflow
- ✅ Uses Reddit's free public JSON API (no API key needed)
- ✅ Uses local Ollama for reply generation (no OpenAI/Claude API)
- ✅ Runs completely offline after setup
- ✅ SQLite database for persistence

**Discovery Engine:** Adapted from [last30days-skill](https://github.com/mvanhorn/last30days-skill) Reddit collection logic.

## 📋 Requirements

- **Python 3.8+**
- **Ollama** with llama3 model installed
- Internet connection (for Reddit discovery only)

## 🚀 Setup

### 1. Install Ollama

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama
ollama serve

# Pull llama3 model
ollama pull llama3
```

### 2. Install Python Dependencies

```bash
cd aila_waitlist_agent

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env if needed (defaults should work)
# Default: Ollama at localhost:11434, llama3 model
```

## 🎮 Usage

### Run the Discovery Pipeline

```bash
python3 run_pipeline.py
```

This will:
1. Search Reddit for travel pain point discussions (last 30 days)
2. Extract top comments from promising posts
3. Score each post as a potential lead (0-100)
4. Generate one final reply for top leads using Ollama
5. Save everything to `data/waitlist_leads.db`

**Options:**
```bash
# Skip comment extraction (faster but less context)
python3 run_pipeline.py --skip-comments

# Skip reply generation (discovery only)
python3 run_pipeline.py --skip-drafting

# Generate replies for top 10 leads only
python3 run_pipeline.py --max-drafts 10

# Customize comment enrichment
python3 run_pipeline.py --max-comments 20
```

### Launch the Review Dashboard

```bash
python3 launch_dashboard.py
```

Opens at `http://localhost:8501`

Dashboard features:
- **View all leads** sorted by score
- **Filter** by status (new, approved, rejected, posted)
- **Review** the final generated reply
- **Approve/Reject** leads
- **Mark as posted** after you manually post
- **Statistics** sidebar

### Workflow

1. **Run pipeline** nightly or weekly: `python3 run_pipeline.py`
2. **Review leads** in dashboard: `python3 launch_dashboard.py`
3. **Approve** high-quality leads with good replies
4. **Manually copy** approved replies to Reddit
5. **Mark as posted** in dashboard to track

## 📂 Project Structure

```
aila_waitlist_agent/
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── .env.example               # Environment template
├── run_pipeline.py            # Main pipeline runner
├── launch_dashboard.py        # Dashboard launcher
│
├── config/                    # Configuration
│   ├── settings.py           # Global settings
│   ├── sources.py            # Reddit sources/queries
│   └── scoring.py            # Scoring weights/keywords
│
├── src/                       # Source code
│   ├── collectors/           # Reddit discovery
│   │   ├── discovery_adapter.py      # Reddit API wrapper
│   │   ├── reddit_recent_collector.py # Main collector
│   │   └── comment_extractor.py      # Comment fetcher
│   │
│   ├── scoring/              # Lead scoring
│   │   ├── lead_scorer.py    # Score calculation
│   │   └── ranker.py         # Ranking & filtering
│   │
│   ├── llm/                  # Reply generation
│   │   ├── ollama_client.py  # Ollama interface
│   │   ├── reply_generator.py # Final reply generation
│   │   └── prompts.py        # Prompt templates
│   │
│   ├── storage/              # Database
│   │   ├── database.py       # SQLite operations
│   │   ├── repository.py     # High-level API
│   │   └── models.py         # Data models
│   │
│   ├── pipeline/             # Orchestration
│   │   ├── discovery_pipeline.py  # Discovery flow
│   │   ├── drafting_pipeline.py   # Reply generation flow
│   │   └── deduper.py            # Deduplication
│   │
│   └── utils/                # Utilities
│       ├── logger.py         # Logging config
│       ├── date_utils.py     # Date helpers
│       └── text_utils.py     # Text processing
│
├── app/                      # Dashboard
│   └── streamlit_app.py     # Streamlit UI
│
├── data/                     # Data storage
│   ├── waitlist_leads.db    # SQLite database (auto-created)
│   ├── raw/                 # Raw data cache
│   ├── processed/           # Processed data
│   └── exports/             # Export files
│
├── logs/                     # Log files
│   └── pipeline.log         # Pipeline logs
│
└── tests/                    # Test data
    └── sample_inputs.json   # Sample posts/comments
```

## 🎯 Scoring Logic

Leads are scored 0-100 based on:

| Component | Weight | What It Measures |
|-----------|--------|------------------|
| **Pain Points** | 30% | Mentions of travel app frustrations, planning stress, organization problems |
| **Request** | 25% | Explicit asks for help, recommendations, advice |
| **Engagement** | 20% | Reddit upvotes and comments (community validation) |
| **Recency** | 15% | How recent the post is (fresher = better) |
| **Quality** | 10% | Post length, detail, specificity |

**Matched Keywords:**
- High intent: "too many apps", "overwhelmed", "frustrated", "struggle"
- Planning: "itinerary", "organize", "planning stress"
- Seeking help: "recommend", "looking for", "need help"

## 💬 Final Reply Style

For each selected lead, Ollama generates one final reply. Replies are designed to:
- Sound human and natural
- Be short (2-4 sentences)
- Provide genuine value first
- Position Aila as something being built, not already launched
- Make sense to other people reading the thread later
- Naturally invite relevant people to the waitlist
- Avoid spam/marketing tone

## 🧪 Testing Locally

### Test Ollama Connection

```bash
python3 -c "from src.llm.ollama_client import test_ollama_connection; test_ollama_connection()"
```

### Test Reply Generation

```bash
python3 -c "from src.llm.reply_generator import test_reply_generation; test_reply_generation()"
```

### Test Discovery

```bash
# Discovery only (no drafting)
python3 run_pipeline.py --skip-drafting --max-comments 5
```

### Check Database

```bash
sqlite3 data/waitlist_leads.db

# View all leads
SELECT post_id, title, lead_score, status FROM leads ORDER BY lead_score DESC LIMIT 10;

# Count by status
SELECT status, COUNT(*) FROM leads GROUP BY status;
```

## 📅 Scheduling Nightly Runs

### Option 1: Cron (Linux/macOS)

```bash
# Edit crontab
crontab -e

# Add nightly run at 2 AM
0 2 * * * cd /path/to/aila_waitlist_agent && /path/to/venv/bin/python3 run_pipeline.py >> logs/cron.log 2>&1
```

### Option 2: launchd (macOS)

Create `~/Library/LaunchAgents/com.aila.waitlist.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.aila.waitlist</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/venv/bin/python3</string>
        <string>/path/to/aila_waitlist_agent/run_pipeline.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>/path/to/aila_waitlist_agent</string>
    <key>StandardOutPath</key>
    <string>/path/to/aila_waitlist_agent/logs/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/aila_waitlist_agent/logs/launchd.err</string>
</dict>
</plist>
```

Load:
```bash
launchctl load ~/Library/LaunchAgents/com.aila.waitlist.plist
```

### Option 3: Manual Runs

Just run it when you want fresh leads:
```bash
python3 run_pipeline.py
```

## 📊 Output Examples

### Console Output

```
==============================================================
STARTING DISCOVERY PIPELINE
==============================================================

[1/4] Collecting Reddit posts...
Starting subreddit collection: 5 queries × 6 subreddits = 30 searches
Collected 180 posts from subreddit searches
Starting global Reddit search: 12 queries
Collected 220 posts from global search
Deduplication: 400 → 285 unique posts

[2/4] Enriching top 30 posts with comments...
Comment enrichment complete

[3/4] Scoring posts...
Scoring complete

[4/4] Ranking and filtering leads...
Filtering: 285 posts → 67 above threshold (40)
Selected top 50 leads

==============================================================
RANKING SUMMARY
==============================================================
Total posts scored: 285
Score range: 12.5 - 87.3 (avg: 45.2)

Top matched keywords:
  'itinerary': 45 posts
  'planning stress': 38 posts
  'recommend': 52 posts

Top 10 leads:
  1. [87.3] r/solotravel: Looking for comprehensive travel planning app...
      → Pain points: itinerary, planning stress | Asks for: recommend, help
```

### Dashboard View

![Dashboard example - showing leads sorted by score with final replies]

## 🛠️ Configuration

Edit `config/` files to customize:

**`config/sources.py`** - Subreddits and search queries
```python
TRAVEL_SUBREDDITS = [
    "travel",
    "solotravel",
    "TravelHacks",
    # Add more...
]

TRAVEL_PAIN_QUERIES = [
    "travel app recommendations",
    "itinerary organization",
    # Add more...
]
```

**`config/scoring.py`** - Keywords and weights
```python
PAIN_POINT_KEYWORDS = {
    "too many apps": 10,
    "overwhelmed": 8,
    # Add more...
}

SCORING_WEIGHTS = {
    "pain_points": 0.30,
    "request": 0.25,
    # Adjust weights...
}
```

**`.env`** - Runtime settings
```bash
OLLAMA_MODEL=llama3         # Change model
MIN_LEAD_SCORE=5            # Adjust threshold
MAX_LEADS_TO_KEEP=50        # Max leads to keep after ranking
MAX_LEADS_TO_DRAFT=5        # Final replies to generate per run
```

## 🔒 Privacy & Ethics

- **Reddit's TOS:** Uses public JSON API, respects rate limits
- **No auto-posting:** All replies are manually reviewed and posted by you
- **Local-first:** Data stays on your machine
- **Transparent:** Replies should identify you as Aila team member

**Best practices:**
- Don't spam
- Provide genuine value in replies
- Be transparent about your affiliation
- Don't post the same reply multiple times
- Respect Reddit community rules

## 🐛 Troubleshooting

### Ollama Connection Failed

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve

# Check model is installed
ollama list
```

### No Leads Found

- Reddit may be rate limiting - wait and try again
- Adjust `MIN_LEAD_SCORE` in `.env` to lower threshold
- Check `logs/pipeline.log` for errors
- Try broader search queries in `config/sources.py`

### Dashboard Won't Start

```bash
# Check Streamlit is installed
pip install streamlit

# Try direct launch
streamlit run app/streamlit_app.py
```

### Database Issues

```bash
# Reset database (WARNING: deletes all data)
rm data/waitlist_leads.db

# Run pipeline to recreate
python3 run_pipeline.py
```

## 📈 Next Steps

1. **Run it nightly** to build a pipeline of leads
2. **Review 5-10 leads/day** in dashboard
3. **Refine the single reply prompt** as you learn what resonates
4. **Track conversion** - how many replies → waitlist signups
5. **Expand sources** - add more subreddits as you find them

## 🤝 Credits

- **Discovery engine:** Adapted from [last30days-skill](https://github.com/mvanhorn/last30days-skill) by @mvanhorn
- **Local LLM:** Powered by [Ollama](https://ollama.com/)
- **Dashboard:** Built with [Streamlit](https://streamlit.io/)

## 📝 License

This is a private tool for Aila's internal use.

---

**Questions?** Check `logs/pipeline.log` for detailed execution logs.

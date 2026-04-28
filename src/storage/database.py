"""
Database module - SQLite storage for leads.

Manages lead persistence, status updates, and queries.
"""

import sqlite3
import json
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from datetime import datetime

from .models import Lead, LeadStatus
from ..utils.logger import get_logger
from config.settings import DATABASE_PATH

logger = get_logger(__name__)


class LeadsDatabase:
    """SQLite database for managing waitlist leads."""

    def __init__(self, db_path: Path = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path or DATABASE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = None
        self.init_database()

    def init_database(self):
        """Initialize database schema."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row  # Enable column access by name

        cursor = self.conn.cursor()

        # Create leads table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                subreddit TEXT NOT NULL,
                source TEXT DEFAULT 'reddit',
                source_id TEXT,
                author TEXT,
                selftext TEXT,
                score INTEGER,
                num_comments INTEGER,
                created_utc REAL,
                lead_score REAL NOT NULL,
                score_breakdown TEXT,
                lead_type TEXT DEFAULT 'post',
                reddit_username TEXT,
                comment_text TEXT,
                parent_post_url TEXT,
                reply TEXT,
                reply_sources TEXT,
                subreddit_policy_mode TEXT DEFAULT 'disallow_promo',
                promo_mode TEXT DEFAULT 'disallowed_or_unclear',
                link_allowed INTEGER DEFAULT 0,
                mention_allowed INTEGER DEFAULT 0,
                actionable_for_promotion INTEGER DEFAULT 0,
                promotion_allowed INTEGER DEFAULT 0,
                link_included INTEGER DEFAULT 0,
                aila_mentioned INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'new',
                discovered_at TEXT NOT NULL,
                updated_at TEXT,
                notes TEXT
            )
        """)

        # Migrate existing tables to add new columns
        self._migrate_schema(cursor)

        # Create index on status for filtering
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status ON leads(status)
        """)

        # Create index on lead_score for sorting
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_lead_score ON leads(lead_score DESC)
        """)

        # Create index on lead_type for filtering
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_lead_type ON leads(lead_type)
        """)

        self.conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def _migrate_schema(self, cursor):
        """Add new columns to existing tables if they don't exist."""
        # Check if new columns exist
        cursor.execute("PRAGMA table_info(leads)")
        columns = {row[1] for row in cursor.fetchall()}

        # Add lead_type if missing
        if 'lead_type' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN lead_type TEXT DEFAULT 'post'")
            logger.info("Added lead_type column")

        # Add reddit_username if missing
        if 'reddit_username' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN reddit_username TEXT")
            logger.info("Added reddit_username column")

        if 'source' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN source TEXT DEFAULT 'reddit'")
            logger.info("Added source column")

        if 'source_id' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN source_id TEXT")
            logger.info("Added source_id column")

        # Add comment_text if missing
        if 'comment_text' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN comment_text TEXT")
            logger.info("Added comment_text column")

        # Add parent_post_url if missing
        if 'parent_post_url' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN parent_post_url TEXT")
            logger.info("Added parent_post_url column")

        if 'reply' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN reply TEXT")
            logger.info("Added reply column")

        if 'reply_sources' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN reply_sources TEXT")
            logger.info("Added reply_sources column")

        if 'subreddit_policy_mode' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN subreddit_policy_mode TEXT DEFAULT 'disallow_promo'")
            logger.info("Added subreddit_policy_mode column")

        if 'promo_mode' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN promo_mode TEXT DEFAULT 'disallowed_or_unclear'")
            logger.info("Added promo_mode column")

        if 'link_allowed' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN link_allowed INTEGER DEFAULT 0")
            logger.info("Added link_allowed column")

        if 'mention_allowed' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN mention_allowed INTEGER DEFAULT 0")
            logger.info("Added mention_allowed column")

        if 'actionable_for_promotion' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN actionable_for_promotion INTEGER DEFAULT 0")
            logger.info("Added actionable_for_promotion column")

        if 'promotion_allowed' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN promotion_allowed INTEGER DEFAULT 0")
            logger.info("Added promotion_allowed column")

        if 'link_included' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN link_included INTEGER DEFAULT 0")
            logger.info("Added link_included column")

        if 'aila_mentioned' not in columns:
            cursor.execute("ALTER TABLE leads ADD COLUMN aila_mentioned INTEGER DEFAULT 0")
            logger.info("Added aila_mentioned column")

    def insert_lead(self, lead: Lead) -> int:
        """
        Insert a new lead.

        Args:
            lead: Lead instance

        Returns:
            post_id of inserted lead
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO leads (
                url, title, subreddit, source, source_id, author, selftext,
                score, num_comments, created_utc, lead_score,
                score_breakdown, lead_type, reddit_username, comment_text, parent_post_url,
                reply, reply_sources, subreddit_policy_mode, promo_mode, link_allowed,
                mention_allowed, actionable_for_promotion, promotion_allowed, link_included, aila_mentioned,
                status, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            lead.url,
            lead.title,
            lead.subreddit,
            lead.source,
            lead.source_id,
            lead.author,
            lead.selftext,
            lead.score,
            lead.num_comments,
            lead.created_utc,
            lead.lead_score,
            json.dumps(lead.score_breakdown),
            lead.lead_type,
            lead.reddit_username,
            lead.comment_text,
            lead.parent_post_url,
            lead.reply,
            json.dumps(lead.reply_sources),
            lead.subreddit_policy_mode,
            lead.promo_mode,
            int(lead.link_allowed),
            int(lead.mention_allowed),
            int(lead.actionable_for_promotion),
            int(lead.promotion_allowed),
            int(lead.link_included),
            int(lead.aila_mentioned),
            lead.status.value,
            lead.discovered_at.isoformat(),
        ))

        self.conn.commit()

        # Get the inserted post_id
        cursor.execute("SELECT post_id FROM leads WHERE url = ?", (lead.url,))
        row = cursor.fetchone()

        return row["post_id"] if row else None

    def bulk_insert_leads(self, leads: List[Lead]) -> int:
        """
        Bulk insert leads.

        Args:
            leads: List of Lead instances

        Returns:
            Number of new leads inserted
        """
        count = 0

        for lead in leads:
            post_id = self.insert_lead(lead)
            if post_id:
                count += 1

        logger.info(f"Inserted {count} new leads (skipped {len(leads) - count} duplicates)")

        return count

    def get_existing_urls(self, urls: List[str]) -> Set[str]:
        """
        Return the subset of URLs that already exist in the leads table.

        Args:
            urls: Lead URLs to check

        Returns:
            Set of URLs already present in the database
        """
        normalized_urls = [url for url in urls if url]
        if not normalized_urls:
            return set()

        cursor = self.conn.cursor()
        existing_urls: Set[str] = set()

        # SQLite has a bound-parameter limit, so query in chunks.
        chunk_size = 500
        for i in range(0, len(normalized_urls), chunk_size):
            chunk = normalized_urls[i:i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            cursor.execute(
                f"SELECT url FROM leads WHERE url IN ({placeholders})",
                chunk,
            )
            existing_urls.update(row["url"] for row in cursor.fetchall())

        return existing_urls

    def update_status(self, post_id: int, status: LeadStatus, notes: str = None):
        """
        Update lead status.

        Args:
            post_id: Lead post_id
            status: New status
            notes: Optional notes
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE leads
            SET status = ?, updated_at = ?, notes = ?
            WHERE post_id = ?
        """, (status.value, datetime.now().isoformat(), notes, post_id))

        self.conn.commit()

        logger.debug(f"Updated lead {post_id} status to {status.value}")

    def get_leads_by_status(self, status: LeadStatus = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get leads by status.

        Args:
            status: Filter by status (None = all)
            limit: Maximum number of leads

        Returns:
            List of lead dicts
        """
        cursor = self.conn.cursor()

        if status:
            cursor.execute("""
                SELECT * FROM leads
                WHERE status = ?
                ORDER BY lead_score DESC, discovered_at DESC
                LIMIT ?
            """, (status.value, limit))
        else:
            cursor.execute("""
                SELECT * FROM leads
                ORDER BY lead_score DESC, discovered_at DESC
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()

        leads = []
        for row in rows:
            lead_dict = dict(row)
            # Parse JSON fields
            if lead_dict.get("score_breakdown"):
                lead_dict["score_breakdown"] = json.loads(lead_dict["score_breakdown"])
            if lead_dict.get("reply_sources"):
                lead_dict["reply_sources"] = json.loads(lead_dict["reply_sources"])
            else:
                lead_dict["reply_sources"] = []
            lead_dict["promotion_allowed"] = bool(lead_dict.get("promotion_allowed"))
            lead_dict["link_allowed"] = bool(lead_dict.get("link_allowed"))
            lead_dict["mention_allowed"] = bool(lead_dict.get("mention_allowed"))
            lead_dict["actionable_for_promotion"] = bool(lead_dict.get("actionable_for_promotion"))
            lead_dict["link_included"] = bool(lead_dict.get("link_included"))
            lead_dict["aila_mentioned"] = bool(lead_dict.get("aila_mentioned"))
            leads.append(lead_dict)

        return leads

    def get_lead_by_id(self, post_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a single lead by ID.

        Args:
            post_id: Lead post_id

        Returns:
            Lead dict or None
        """
        cursor = self.conn.cursor()

        cursor.execute("SELECT * FROM leads WHERE post_id = ?", (post_id,))
        row = cursor.fetchone()

        if not row:
            return None

        lead_dict = dict(row)
        if lead_dict.get("score_breakdown"):
            lead_dict["score_breakdown"] = json.loads(lead_dict["score_breakdown"])
        if lead_dict.get("reply_sources"):
            lead_dict["reply_sources"] = json.loads(lead_dict["reply_sources"])
        else:
            lead_dict["reply_sources"] = []
        lead_dict["promotion_allowed"] = bool(lead_dict.get("promotion_allowed"))
        lead_dict["link_allowed"] = bool(lead_dict.get("link_allowed"))
        lead_dict["mention_allowed"] = bool(lead_dict.get("mention_allowed"))
        lead_dict["actionable_for_promotion"] = bool(lead_dict.get("actionable_for_promotion"))
        lead_dict["link_included"] = bool(lead_dict.get("link_included"))
        lead_dict["aila_mentioned"] = bool(lead_dict.get("aila_mentioned"))

        return lead_dict

    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Stats dict
        """
        cursor = self.conn.cursor()

        # Total leads
        cursor.execute("SELECT COUNT(*) as count FROM leads")
        total = cursor.fetchone()["count"]

        # By status
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM leads
            GROUP BY status
        """)
        by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT source, COUNT(*) as count
            FROM leads
            GROUP BY source
        """)
        by_source = {row["source"] or "reddit": row["count"] for row in cursor.fetchall()}

        # Average score
        cursor.execute("SELECT AVG(lead_score) as avg_score FROM leads")
        avg_score = cursor.fetchone()["avg_score"] or 0

        return {
            "total_leads": total,
            "by_status": by_status,
            "by_source": by_source,
            "avg_lead_score": round(avg_score, 2),
        }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.debug("Database connection closed")

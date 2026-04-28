"""
Repository - high-level interface for lead persistence.

Provides a clean API for storing and retrieving leads.
"""

from typing import List, Dict, Any, Set

from .database import LeadsDatabase
from .models import Lead, LeadStatus
from ..utils.logger import get_logger

logger = get_logger(__name__)


class LeadRepository:
    """High-level repository for managing leads."""

    def __init__(self, database: LeadsDatabase = None):
        """
        Initialize repository.

        Args:
            database: Optional LeadsDatabase instance
        """
        self.db = database or LeadsDatabase()

    def save_discovered_leads(self, leads_data: List[Dict[str, Any]]) -> int:
        """
        Save discovered leads to database.

        Args:
            leads_data: List of lead dicts (from pipeline)

        Returns:
            Number of new leads saved
        """
        logger.info(f"Saving {len(leads_data)} discovered leads to database...")

        # Convert dicts to Lead models
        leads = [Lead.from_dict(data) for data in leads_data]

        # Bulk insert
        count = self.db.bulk_insert_leads(leads)

        logger.info(f"Saved {count} new leads")

        return count

    def get_existing_lead_urls(self, urls: List[str]) -> Set[str]:
        """
        Return the subset of lead URLs that already exist in storage.

        Args:
            urls: Lead URLs to check

        Returns:
            Set of URLs already present in the database
        """
        return self.db.get_existing_urls(urls)

    def get_new_leads(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get leads with 'new' status.

        Args:
            limit: Maximum number

        Returns:
            List of lead dicts
        """
        return self.db.get_leads_by_status(LeadStatus.NEW, limit=limit)

    def get_approved_leads(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get approved leads ready for posting.

        Args:
            limit: Maximum number

        Returns:
            List of lead dicts
        """
        return self.db.get_leads_by_status(LeadStatus.APPROVED, limit=limit)

    def get_all_leads(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all leads regardless of status.

        Args:
            limit: Maximum number

        Returns:
            List of lead dicts
        """
        return self.db.get_leads_by_status(None, limit=limit)

    def approve_lead(self, post_id: int, notes: str = None):
        """Mark lead as approved."""
        self.db.update_status(post_id, LeadStatus.APPROVED, notes)

    def reject_lead(self, post_id: int, notes: str = None):
        """Mark lead as rejected."""
        self.db.update_status(post_id, LeadStatus.REJECTED, notes)

    def mark_posted(self, post_id: int, notes: str = None):
        """Mark lead as posted."""
        self.db.update_status(post_id, LeadStatus.POSTED, notes)

    def get_statistics(self) -> Dict[str, Any]:
        """Get repository statistics."""
        return self.db.get_stats()

    def close(self):
        """Close database connection."""
        self.db.close()

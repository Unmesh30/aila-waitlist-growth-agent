"""
Date utilities.

Helper functions for date parsing and formatting.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional


def timestamp_to_datetime(timestamp: float) -> datetime:
    """
    Convert Unix timestamp to datetime.

    Args:
        timestamp: Unix timestamp

    Returns:
        Datetime object in UTC
    """
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def timestamp_to_date_string(timestamp: float) -> str:
    """
    Convert Unix timestamp to date string.

    Args:
        timestamp: Unix timestamp

    Returns:
        Date string (YYYY-MM-DD)
    """
    dt = timestamp_to_datetime(timestamp)
    return dt.strftime("%Y-%m-%d")


def days_ago(days: int) -> datetime:
    """
    Get datetime N days ago.

    Args:
        days: Number of days

    Returns:
        Datetime object
    """
    return datetime.now(timezone.utc) - timedelta(days=days)


def format_relative_time(timestamp: float) -> str:
    """
    Format timestamp as relative time (e.g., "2 days ago").

    Args:
        timestamp: Unix timestamp

    Returns:
        Relative time string
    """
    dt = timestamp_to_datetime(timestamp)
    now = datetime.now(timezone.utc)
    diff = now - dt

    if diff.days == 0:
        hours = diff.seconds // 3600
        if hours == 0:
            minutes = diff.seconds // 60
            return f"{minutes} min ago"
        return f"{hours} hrs ago"
    elif diff.days == 1:
        return "1 day ago"
    else:
        return f"{diff.days} days ago"


def parse_iso_date(date_string: str) -> Optional[datetime]:
    """
    Parse ISO format date string.

    Args:
        date_string: ISO date string

    Returns:
        Datetime object or None
    """
    try:
        return datetime.fromisoformat(date_string)
    except (ValueError, TypeError):
        return None

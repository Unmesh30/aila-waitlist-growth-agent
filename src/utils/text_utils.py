"""
Text utilities.

Helper functions for text processing and formatting.
"""

import re
from typing import List


def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to append if truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)].rstrip() + suffix


def clean_text(text: str) -> str:
    """
    Clean text for display.

    Args:
        text: Text to clean

    Returns:
        Cleaned text
    """
    # Remove multiple newlines
    text = re.sub(r'\n\s*\n', '\n\n', text)

    # Remove excessive whitespace
    text = re.sub(r' +', ' ', text)

    return text.strip()


def extract_sentences(text: str, max_sentences: int = 3) -> str:
    """
    Extract first N sentences from text.

    Args:
        text: Text to extract from
        max_sentences: Maximum sentences

    Returns:
        Extracted sentences
    """
    # Simple sentence splitting
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    return '. '.join(sentences[:max_sentences]) + '.'


def highlight_keywords(text: str, keywords: List[str], max_length: int = 200) -> str:
    """
    Highlight keywords in text and truncate around them.

    Args:
        text: Text to process
        keywords: Keywords to highlight
        max_length: Maximum length

    Returns:
        Processed text with highlighted keywords
    """
    text_lower = text.lower()

    # Find first keyword occurrence
    first_pos = len(text)
    for keyword in keywords:
        pos = text_lower.find(keyword.lower())
        if pos != -1 and pos < first_pos:
            first_pos = pos

    # If keyword found, center text around it
    if first_pos < len(text):
        start = max(0, first_pos - max_length // 2)
        end = min(len(text), start + max_length)

        excerpt = text[start:end]

        if start > 0:
            excerpt = "..." + excerpt
        if end < len(text):
            excerpt = excerpt + "..."

        return excerpt

    # No keywords found, just truncate
    return truncate(text, max_length)


def contains_any(text: str, keywords: List[str], case_sensitive: bool = False) -> bool:
    """
    Check if text contains any of the keywords.

    Args:
        text: Text to check
        keywords: List of keywords
        case_sensitive: Whether to match case

    Returns:
        True if any keyword found
    """
    if not case_sensitive:
        text = text.lower()
        keywords = [k.lower() for k in keywords]

    return any(keyword in text for keyword in keywords)

"""
Lightweight source grounding for reply generation.

Looks up official or otherwise highly trustworthy sources only when a lead
appears to require factual or policy-based guidance.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus, urlparse

import requests

from ..utils.logger import get_logger
from config.settings import GROUNDING_TIMEOUT, GROUNDING_MAX_SOURCES

logger = get_logger(__name__)


OFFICIAL_DOMAIN_GROUPS = {
    "visa_policy": [
        "travel.state.gov",
        "state.gov",
        "cbp.gov",
        "uscis.gov",
        "gov.uk",
        "homeaffairs.gov.au",
        "canada.ca",
        "europa.eu",
        "eeas.europa.eu",
        "iata.org",
    ],
    "airline_policy": [
        "aa.com",
        "united.com",
        "delta.com",
        "alaskaair.com",
        "southwest.com",
        "jetblue.com",
        "britishairways.com",
        "lufthansa.com",
        "airfrance.com",
        "klm.com",
        "ryanair.com",
        "easyjet.com",
        "emirates.com",
        "qatarairways.com",
        "singaporeair.com",
        "iata.org",
    ],
    "rail_transit": [
        "amtrak.com",
        "nationalrail.co.uk",
        "eurail.com",
        "eurostar.com",
        "bahn.com",
        "trenitalia.com",
        "renfe.com",
        "sncf-connect.com",
        "tfl.gov.uk",
    ],
    "tourism": [
        "visitbritain.com",
        "nycgo.com",
        "france.fr",
        "japan.travel",
        "australia.com",
        "visiteurope.com",
    ],
}

FACTUAL_PATTERNS = {
    "visa_policy": [
        "visa", "passport", "entry requirement", "immigration", "transit visa",
        "travel advisory", "citizenship", "customs", "border", "eta", "esta",
    ],
    "airline_policy": [
        "airline", "baggage", "carry on", "carry-on", "checked bag", "rebook",
        "refund", "boarding", "layover", "missed connection", "flight policy",
        "cancellation", "delayed flight",
    ],
    "rail_transit": [
        "train", "rail", "metro", "subway", "station", "transit pass", "eurail",
        "amtrak", "eurostar",
    ],
}


def _normalize_text(lead: Dict[str, Any]) -> str:
    return " ".join(
        str(part or "")
        for part in [
            lead.get("title"),
            lead.get("selftext"),
            lead.get("comment_text"),
        ]
    ).lower()


def detect_grounding_need(lead: Dict[str, Any]) -> Tuple[bool, Optional[str], str]:
    """
    Decide whether the lead needs factual grounding and which source group to use.
    """
    text = _normalize_text(lead)

    for group, patterns in FACTUAL_PATTERNS.items():
        if any(pattern in text for pattern in patterns):
            return True, group, text

    return False, None, text


def _build_queries(lead: Dict[str, Any], source_group: str) -> List[str]:
    title = str(lead.get("title", "")).strip()
    text = str(lead.get("selftext") or lead.get("comment_text") or "").strip()
    base = title or text[:120]
    base = re.sub(r"\s+", " ", base).strip()

    domains = OFFICIAL_DOMAIN_GROUPS.get(source_group, [])
    queries = []
    for domain in domains[:6]:
        queries.append(f"site:{domain} {base}")

    if not queries:
        queries.append(base)

    return queries[:6]


def _search_duckduckgo(query: str) -> List[Tuple[str, str]]:
    """
    Lightweight HTML search. Returns (title, url) pairs.
    """
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=GROUNDING_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(f"Grounding search failed for '{query}': {exc}")
        return []

    matches = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        response.text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    results = []
    for href, title_html in matches:
        title = re.sub(r"<.*?>", "", unescape(title_html)).strip()
        if href and title:
            results.append((title, href))

    return results


def _is_allowed_domain(domain: str, allowed_domains: List[str]) -> bool:
    """True for an exact match or a real subdomain of an allowlisted domain.

    "travel.state.gov" passes "state.gov", but "visa-help-gov.uk" does not pass "gov.uk"
    and "baa.com" does not pass "aa.com" (a plain endswith check let both through).
    """
    domain = (domain or "").lower().rstrip(".")
    return any(domain == allowed or domain.endswith("." + allowed) for allowed in allowed_domains)


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _fetch_snippet(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=GROUNDING_TIMEOUT)
        response.raise_for_status()
        text = response.text
    except requests.RequestException as exc:
        logger.warning(f"Grounding fetch failed for '{url}': {exc}")
        return ""

    # Prefer meta description, fall back to first text chunk.
    meta_match = re.search(
        r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
        text,
        flags=re.IGNORECASE,
    )
    if meta_match:
        return unescape(meta_match.group(1)).strip()[:280]

    body_text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    body_text = re.sub(r"<.*?>", " ", body_text)
    body_text = re.sub(r"\s+", " ", unescape(body_text)).strip()
    return body_text[:280]


def gather_sources_for_lead(lead: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Retrieve a few official or trustworthy sources for a factual lead.
    """
    needs_grounding, source_group, _ = detect_grounding_need(lead)
    if not needs_grounding or not source_group:
        return []

    queries = _build_queries(lead, source_group)
    allowed_domains = OFFICIAL_DOMAIN_GROUPS.get(source_group, [])
    seen_urls = set()
    sources: List[Dict[str, str]] = []

    for query in queries:
        for title, url in _search_duckduckgo(query):
            domain = _extract_domain(url)
            if not _is_allowed_domain(domain, allowed_domains):
                continue
            if url in seen_urls:
                continue

            snippet = _fetch_snippet(url)
            if not snippet:
                continue

            seen_urls.add(url)
            sources.append({
                "title": title,
                "url": url,
                "snippet": snippet,
                "domain": domain,
            })

            if len(sources) >= GROUNDING_MAX_SOURCES:
                return sources

    return sources


def format_sources_for_prompt(sources: List[Dict[str, str]]) -> str:
    """Compact source context for the reply prompt."""
    if not sources:
        return ""

    lines = []
    for source in sources[:GROUNDING_MAX_SOURCES]:
        lines.append(
            f"- {source['title']} ({source['domain']}): {source['snippet']}"
        )
    return "\n".join(lines)

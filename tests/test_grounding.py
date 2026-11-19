from src.llm import source_grounder
from src.llm.source_grounder import OFFICIAL_DOMAIN_GROUPS, _is_allowed_domain, gather_sources_for_lead

VISA = OFFICIAL_DOMAIN_GROUPS["visa_policy"]
AIRLINES = OFFICIAL_DOMAIN_GROUPS["airline_policy"]


def test_exact_domains_and_real_subdomains_pass():
    assert _is_allowed_domain("state.gov", VISA)
    assert _is_allowed_domain("travel.state.gov", VISA)
    assert _is_allowed_domain("www.gov.uk", VISA)


def test_look_alike_domains_are_rejected():
    assert not _is_allowed_domain("visa-help-gov.uk", VISA)
    assert not _is_allowed_domain("baa.com", AIRLINES)
    assert not _is_allowed_domain("travel.state.gov.example.net", VISA)
    assert not _is_allowed_domain("", VISA)


def test_only_allowlisted_official_pages_reach_a_reply(monkeypatch):
    results = [
        ("Travel blog", "https://travel-blog.example.com/schengen"),
        ("Look-alike", "https://visa-help-gov.uk/schengen"),
        ("US State Department", "https://travel.state.gov/content/travel/en/international-travel.html"),
        ("EU", "https://europa.eu/youreurope/citizens/travel/entry-exit/index_en.htm"),
    ]
    monkeypatch.setattr(source_grounder, "_search_duckduckgo", lambda query: results)
    monkeypatch.setattr(source_grounder, "_fetch_snippet", lambda url: "snippet")
    lead = {"title": "Do I need a visa for a Schengen stopover?", "selftext": "Entry requirements?"}
    domains = [source["domain"] for source in gather_sources_for_lead(lead)]
    assert domains == ["travel.state.gov", "europa.eu"]

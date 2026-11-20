from demo import DemoLLMClient
from src.llm.reply_generator import ReplyGenerator

REPLY = (
    "Keeping everything in one place helps. "
    "We're building Aila, an all-in-one travel planner, for exactly this: https://joinaila.com/"
)


def _sanitize(allow_mention, allow_link):
    return ReplyGenerator(ollama_client=DemoLLMClient())._sanitize_reply(
        REPLY, allow_aila_mention=allow_mention, allow_link=allow_link
    )


def test_link_is_kept_where_the_community_allows_links():
    assert "https://joinaila.com/" in _sanitize(True, True)


def test_link_is_removed_cleanly_where_only_a_mention_is_allowed():
    cleaned = _sanitize(True, False)
    assert "joinaila.com" not in cleaned
    assert "Aila" in cleaned
    assert cleaned.endswith(".")
    assert not cleaned.rstrip(".").endswith(":")


def test_every_promotional_sentence_is_removed_where_promotion_is_not_allowed():
    cleaned = _sanitize(False, False)
    assert "aila" not in cleaned.lower()
    assert "joinaila" not in cleaned.lower()
    assert cleaned == "Keeping everything in one place helps."


def _clean(text, allow_link=False, source_urls=None):
    return ReplyGenerator(ollama_client=DemoLLMClient())._sanitize_reply(
        text, allow_aila_mention=True, allow_link=allow_link, source_urls=source_urls
    )


def test_invented_links_and_handles_are_removed():
    cleaned = _clean(
        "Check out our app @AilaTravel for this. [AirlineWise](https://airlinewise.com/) suggests one document.",
        allow_link=True,
    )
    assert cleaned == "Check out our app for this. AirlineWise suggests one document."


def test_links_to_the_official_sources_given_are_kept():
    text = "See [the State Department](https://travel.state.gov/entry) for the entry rules."
    assert _clean(text, source_urls=["https://travel.state.gov/entry"]) == text
    assert _clean(text) == "See the State Department for the entry rules."


def test_a_markdown_waitlist_link_goes_with_its_at():
    text = "Join our waitlist at [https://joinaila.com/](https://joinaila.com/) so you can be first."
    assert _clean(text) == "Join our waitlist so you can be first."


def test_paragraphs_and_endings_are_left_alone():
    text = "First tip.\n\n1. Book flights first.\n2. Then stays.\n\nHope that helps! 🚀"
    assert _clean(text) == text


def test_copied_instructions_invented_stories_and_broken_sign_up_lines_are_removed():
    raw = (
        "I've been there! Keep one shared spreadsheet.\n\n"
        "We're building Aila, an all-in-one travel planner. Check out https://joinaila.com/ later.\n\n"
        "https://joinaila.com/ (when direct link is allowed)\n\n"
        "[Join our waitlist at https://joinaila.com/ if you want updates!]"
    )
    assert _clean(raw) == (
        "Keep one shared spreadsheet.\n\n"
        "We're building Aila, an all-in-one travel planner.\n\n"
        "Join our waitlist if you want updates!"
    )

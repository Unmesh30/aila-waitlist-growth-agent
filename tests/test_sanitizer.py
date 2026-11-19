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

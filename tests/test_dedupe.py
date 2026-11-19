from src.pipeline.deduper import deduplicate_by_url, deduplicate_comments


def test_duplicate_urls_are_dropped_keeping_the_first():
    posts = [
        {"url": "https://example.org/a", "title": "first"},
        {"url": "https://example.org/b", "title": "other"},
        {"url": "https://example.org/a", "title": "repeat"},
        {"title": "no url"},
    ]
    unique = deduplicate_by_url(posts)
    assert [p["title"] for p in unique] == ["first", "other"]


def test_duplicate_comment_bodies_are_dropped():
    comments = [{"body": "Same here"}, {"body": " Same here "}, {"body": "Different"}, {"body": ""}]
    assert [c["body"].strip() for c in deduplicate_comments(comments)] == ["Same here", "Different"]

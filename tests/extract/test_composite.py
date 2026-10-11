from pathlib import Path

import pytest
from builders import make_item

from auto_biblio.domain.errors import ExtractionError
from auto_biblio.extract.composite import CompositeExtractor


class Fetcher:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.keys: list[str] = []

    def fetch(self, key: str) -> str:
        self.keys.append(key)
        if self.text is None:
            message = "boom"
            raise ExtractionError(key, message)
        return self.text


def extractor(tmp_path: Path | None = None, **fetchers: Fetcher) -> CompositeExtractor:
    return CompositeExtractor(
        fetchers.get("arxiv", Fetcher()),
        fetchers.get("repo", Fetcher()),
        fetchers.get("article", Fetcher()),
        tmp_path,
    )


def test_dispatch_arxiv_with_cap_and_links() -> None:
    arxiv = Fetcher("Intro https://github.com/o/r body.\nReferences\n[1] x")
    out = extractor(arxiv=arxiv).extract(make_item(item_id="arxiv:2410.1"), 1000)
    assert arxiv.keys == ["2410.1"]
    assert out.source == "full_text"
    assert out.text == "Intro https://github.com/o/r body."
    assert out.links == ("https://github.com/o/r",)


def test_dispatch_release_uses_repo() -> None:
    repo = Fetcher("Readme")
    item = make_item(item_id="gh:o/r@v1", source_type="github_releases", kind="release")
    assert extractor(repo=repo).extract(item, 100).text == "Readme"
    assert repo.keys == ["o/r"]


def test_dispatch_article() -> None:
    article = Fetcher("Post body")
    item = make_item(item_id="url:a", source_type="rss", kind="blog_post")
    assert extractor(article=article).extract(item, 100).source == "full_text"
    assert article.keys == ["https://example.com/x"]


def test_all_fail_falls_back_to_summary_then_title() -> None:
    out = extractor().extract(make_item(summary="Abstract https://x.org"), 100)
    assert (out.source, out.text, out.links) == (
        "abstract",
        "Abstract https://x.org",
        ("https://x.org",),
    )
    assert out.errors
    bare = extractor().extract(make_item(title="T", summary=None), 100)
    assert (bare.source, bare.text) == ("title", "T")


def test_discussion_without_external_link() -> None:
    item = make_item(
        item_id="url:hn", source_type="hackernews", kind="discussion", summary="Ask HN"
    )
    item = item.model_copy(update={"url": "https://news.ycombinator.com/item?id=1"})
    article = Fetcher("never")
    out = extractor(article=article).extract(item, 100)
    assert out.source == "abstract"
    assert article.keys == []


def test_cache_hit_no_network(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    arxiv = Fetcher("Full text " * 10)
    item = make_item(item_id="arxiv:2410.1")
    first = extractor(tmp_path, arxiv=arxiv).extract(item, 1000)
    again = extractor(tmp_path, arxiv=Fetcher()).extract(item, 15)
    assert first.source == again.source == "full_text"
    assert again.text == "Full text Full"
    assert arxiv.keys == ["2410.1"]
    next(tmp_path.glob("*.json")).write_text("{broken")
    assert extractor(tmp_path, arxiv=Fetcher()).extract(item, 100).source == "abstract"
    assert "unreadable full-text cache" in caplog.text

import re

import pytest

from auto_biblio.domain.ids import ItemId, canonical_id, kind_for, normalize_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://arxiv.org/abs/2410.12345v2", "arxiv:2410.12345"),
        ("http://arxiv.org/pdf/2410.12345v1.pdf", "arxiv:2410.12345"),
        ("https://export.arxiv.org/abs/2410.12345", "arxiv:2410.12345"),
        ("https://huggingface.co/papers/2410.12345", "arxiv:2410.12345"),
        ("https://GitHub.com/Pydantic/Pydantic-AI", "gh:pydantic/pydantic-ai"),
        ("https://github.com/pola-rs/polars/tree/main/py-polars", "gh:pola-rs/polars"),
        ("https://github.com/astral-sh/uv/releases/tag/0.9.1", "gh:astral-sh/uv@0.9.1"),
        ("https://doi.org/10.1000/ABC.def", "doi:10.1000/abc.def"),
    ],
)
def test_canonical_id(url: str, expected: str) -> None:
    assert canonical_id(url) == expected


def test_equivalent_generic_urls_share_id() -> None:
    first = canonical_id("https://www.example.com/post/?utm_source=x&id=3#top")
    second = canonical_id("http://example.com/post?id=3")
    assert first == second
    assert re.fullmatch(r"url:[0-9a-f]{16}", first)


def test_normalize_url_strips_tracking() -> None:
    url = "HTTP://www.Example.com/a/?z=1&ref=hn&source=rss&utm_medium=x&b=2#frag"
    assert normalize_url(url) == "https://example.com/a?b=2&z=1"


def test_github_non_repo_paths_are_urls() -> None:
    assert canonical_id("https://github.com/features").startswith("url:")


def test_kind_for() -> None:
    assert kind_for(ItemId("arxiv:2410.12345"), "blog_post") == "paper"
    assert kind_for(ItemId("doi:10.1/x"), "blog_post") == "paper"
    assert kind_for(ItemId("gh:o/r"), "blog_post") == "repo"
    assert kind_for(ItemId("gh:o/r@v1"), "blog_post") == "release"
    assert kind_for(ItemId("url:0123456789abcdef"), "discussion") == "discussion"

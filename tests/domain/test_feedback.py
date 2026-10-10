import pytest

from auto_biblio.domain.errors import FeedbackParseError
from auto_biblio.domain.feedback import parse_issue_title, parse_issue_week


@pytest.mark.parametrize(
    ("title", "polarity"),
    [("👍 arxiv:2410.12345", 1), ("👎 gh:o/r", -1), ("+1 doi:10.1/x", 1), (" -1 url:abc ", -1)],
)
def test_parse_title(title: str, polarity: int) -> None:
    parsed = parse_issue_title(title, "issue#1")
    assert parsed.polarity == polarity
    assert parsed.item_id.split(":")[0] in {"arxiv", "gh", "doi", "url"}


def test_parse_rejects_unknown_prefix() -> None:
    with pytest.raises(FeedbackParseError, match="unknown item id"):
        parse_issue_title("👍 foo:bar", "issue#2")


@pytest.mark.parametrize("title", ["👍 arxiv:1 and more", "great paper", "👍"])
def test_parse_rejects_malformed(title: str) -> None:
    with pytest.raises(FeedbackParseError, match="issue#3"):
        parse_issue_title(title, "issue#3")


def test_parse_week() -> None:
    assert parse_issue_week("some text\nweek: 2026-W41\n") == "2026-W41"


@pytest.mark.parametrize("body", [None, "", "week: soon"])
def test_parse_week_absent(body: str | None) -> None:
    assert parse_issue_week(body) is None

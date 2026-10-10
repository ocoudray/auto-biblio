from datetime import UTC, datetime
from pathlib import Path

import pytest

from auto_biblio.domain.errors import SourcePayloadError
from auto_biblio.sources._feeds import parse_feed, strip_html

FIXTURES = Path(__file__).parent.parent / "fixtures" / "rss"


def test_parse_atom() -> None:
    entries = parse_feed((FIXTURES / "atom_sample.xml").read_bytes(), source="sw")
    assert len(entries) == 3
    first = entries[0]
    assert first.title == "Quoting The New York Times"
    assert first.link == "https://simonwillison.net/2026/Oct/10/the-new-york-times/"
    assert first.published == datetime(2026, 10, 10, 2, 4, 12, tzinfo=UTC)
    assert first.authors == ("Simon Willison",)
    assert first.summary == "Short note & link."


def test_parse_rss2() -> None:
    entries = parse_feed((FIXTURES / "rss2_sample.xml").read_bytes(), source="hf")
    assert entries[0].link == "https://arxiv.org/abs/2410.12345v1"
    assert entries[0].summary == "A paper about state spaces."
    assert entries[1].published is None
    assert entries[1].summary is None


def test_naive_date_is_utc() -> None:
    entries = parse_feed((FIXTURES / "rss2_sample.xml").read_bytes(), source="hf")
    assert entries[2].published == datetime(2026, 10, 8, 10, 0, tzinfo=UTC)


def test_broken_feed_raises_payload_error() -> None:
    raw = (FIXTURES / "broken.xml").read_bytes()
    with pytest.raises(SourcePayloadError) as excinfo:
        parse_feed(raw, source="bad")
    assert excinfo.value.payload_excerpt.startswith("<rss>")


def test_strip_html_truncates() -> None:
    assert strip_html("<p>a&amp;b\n\n  c</p>") == "a&b c"
    assert len(strip_html("x" * 5000)) == 2000


def rss_with_date(date: str) -> bytes:
    return (
        "<rss version='2.0'><channel><title>t</title><item><title>x</title>"
        f"<link>https://e.com/a</link><pubDate>{date}</pubDate></item></channel></rss>"
    ).encode()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-08 10:00:00", datetime(2026, 10, 8, 10, 0, tzinfo=UTC)),
        ("2026-10-08 12:00:00+02:00", datetime(2026, 10, 8, 10, 0, tzinfo=UTC)),
        ("not a date", None),
    ],
)
def test_unusual_dates(raw: str, expected: datetime | None) -> None:
    (entry,) = parse_feed(rss_with_date(raw), source="s")
    assert entry.published == expected


def test_entries_without_link_are_skipped() -> None:
    raw = (
        b"<rss version='2.0'><channel><title>t</title><item><title>x</title></item></channel></rss>"
    )
    assert parse_feed(raw, source="s") == ()

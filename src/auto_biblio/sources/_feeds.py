"""Typed adapter around `feedparser`, the only module allowed to touch it."""

import calendar
import email.utils
import html
import re
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import cast

# feedparser ships no type information; this adapter turns its untyped output
# into the typed `FeedEntry` model so the rest of the code never sees it.
import feedparser  # pyright: ignore[reportMissingTypeStubs]
from pydantic import AwareDatetime, BaseModel, ConfigDict

from auto_biblio.domain.errors import SourcePayloadError

SUMMARY_MAX = 2000
_BLOCK_TAGS = re.compile(
    r"</?(?:p|div|br|li|ul|ol|h\d|blockquote|tr|td|pre)\b[^>]*>", re.IGNORECASE
)
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


class FeedEntry(BaseModel):
    """One entry of an RSS or Atom feed."""

    model_config = ConfigDict(frozen=True)

    link: str
    title: str
    summary: str | None
    authors: tuple[str, ...]
    published: AwareDatetime | None
    categories: tuple[str, ...]


def strip_html(text: str) -> str:
    """Turn an HTML fragment into compact plain text, truncated to 2000 characters.

    Args:
        text: HTML fragment.

    Returns:
        Plain text.
    """
    without_tags = _TAGS.sub("", _BLOCK_TAGS.sub(" ", text))
    plain = _SPACES.sub(" ", html.unescape(without_tags)).strip()
    return plain[:SUMMARY_MAX]


def parse_feed(content: bytes, *, source: str) -> tuple[FeedEntry, ...]:
    """Parse an RSS or Atom document.

    Entries without a link are skipped. Dates without a timezone are read as UTC.

    Args:
        content: Raw feed document.
        source: Source name, for error messages.

    Returns:
        The feed entries, in document order.

    Raises:
        SourcePayloadError: If the document is malformed and yields no entry.
    """
    # Cast: feedparser returns an untyped FeedParserDict (a dict subclass).
    parsed = cast("Mapping[str, object]", feedparser.parse(content))  # pyright: ignore[reportUnknownMemberType]
    entries = cast("Sequence[Mapping[str, object]]", parsed.get("entries", []))
    if parsed.get("bozo") and not entries:
        excerpt = content.decode("utf-8", errors="replace")
        message = f"malformed feed: {parsed.get('bozo_exception')}"
        raise SourcePayloadError(source, message, excerpt)
    feed = cast("Mapping[str, object]", parsed.get("feed", {}))
    default_authors = _names(feed)
    return tuple(_entry(raw, default_authors) for raw in entries if _text(raw, "link"))


def _entry(raw: Mapping[str, object], default_authors: tuple[str, ...]) -> FeedEntry:
    summary = _text(raw, "summary")
    return FeedEntry(
        link=_text(raw, "link"),
        title=_SPACES.sub(" ", _text(raw, "title")).strip(),
        summary=strip_html(summary) or None,
        authors=_names(raw) or default_authors,
        published=_date(raw),
        categories=tuple(_text(tag, "term") for tag in _mappings(raw, "tags")),
    )


def _text(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    return value if isinstance(value, str) else ""


def _mappings(raw: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = raw.get(key)
    if not isinstance(value, list):
        return []
    items = cast("list[object]", value)
    return [cast("Mapping[str, object]", item) for item in items if isinstance(item, Mapping)]


def _names(raw: Mapping[str, object]) -> tuple[str, ...]:
    names = tuple(name for a in _mappings(raw, "authors") if (name := _text(a, "name")))
    return names or ((author,) if (author := _text(raw, "author")) else ())


def _date(raw: Mapping[str, object]) -> datetime | None:
    # Look at real keys only: reading a missing "updated_parsed" makes feedparser
    # emit a deprecation warning and silently alias another field.
    present = set(raw.keys())
    for key in ("published_parsed", "updated_parsed"):
        value = raw[key] if key in present else None
        if isinstance(value, time.struct_time):
            # feedparser normalizes every date it understands to a UTC struct_time.
            return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)
    for key in ("published", "updated"):
        if key in present and (parsed := _parse_raw_date(_text(raw, key))) is not None:
            return parsed
    return None


def _parse_raw_date(text: str) -> datetime | None:
    """Parse a date feedparser rejected, typically one without a timezone (read as UTC)."""
    try:
        parsed = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)

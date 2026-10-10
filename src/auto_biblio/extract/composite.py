"""Pick the right fetcher for an item, fall back to its summary, and cache the result."""

import hashlib
import logging
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from auto_biblio.domain.errors import ExtractionError
from auto_biblio.domain.models import Item
from auto_biblio.extract import ExtractedText, clean_text, collect_links

logger = logging.getLogger(__name__)

_DISCUSSION_HOSTS = ("news.ycombinator.com", "reddit.com", "www.reddit.com")


class Fetcher(Protocol):
    """Fetches the full text behind a key (arXiv id, `owner/repo`, URL)."""

    def fetch(self, key: str, /) -> str:
        """Fetch a text."""
        ...


class CompositeExtractor:
    """`TextExtractor` dispatching on the item, with fallbacks and an on-disk cache."""

    def __init__(
        self, arxiv: Fetcher, repo: Fetcher, article: Fetcher, cache_dir: Path | None
    ) -> None:
        """Build the extractor.

        Args:
            arxiv: Fetches papers by arXiv id.
            repo: Fetches repositories by `owner/repo`.
            article: Fetches web pages by URL.
            cache_dir: Where full texts are cached (None disables the cache).
        """
        self._arxiv = arxiv
        self._repo = repo
        self._article = article
        self._cache_dir = cache_dir

    def extract(self, item: Item, max_chars: int) -> ExtractedText:
        """Extract the full text of an item, else fall back to its summary or title.

        Args:
            item: The item.
            max_chars: Size cap of the text.

        Returns:
            The text, with `source` telling what it really is.
        """
        cached = self._read_cache(item)
        if cached is not None:
            return _capped(cached, max_chars)
        target = self._target(item)
        if target is None:
            return _fallback(item, ())
        fetcher, key = target
        try:
            raw = fetcher.fetch(key)
        except ExtractionError as exc:
            logger.warning("full text unavailable for %s: %s", item.id, exc)
            return _fallback(item, (str(exc),))
        extracted = ExtractedText(text=raw, source="full_text", links=collect_links(raw))
        self._write_cache(item, extracted)
        return _capped(extracted, max_chars)

    def _target(self, item: Item) -> tuple[Fetcher, str] | None:
        if item.id.startswith("arxiv:"):
            return self._arxiv, item.id.removeprefix("arxiv:")
        if item.id.startswith("gh:"):
            return self._repo, item.id.removeprefix("gh:").split("@", 1)[0]
        url = str(item.url)
        if item.kind == "discussion" and any(host in url for host in _DISCUSSION_HOSTS):
            return None
        return self._article, url

    def _cache_path(self, item: Item) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / f"{hashlib.sha256(item.id.encode()).hexdigest()}.json"

    def _read_cache(self, item: Item) -> ExtractedText | None:
        path = self._cache_path(item)
        if path is None or not path.exists():
            return None
        try:
            return ExtractedText.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            logger.warning("ignoring unreadable full-text cache %s: %s", path, exc)
            return None

    def _write_cache(self, item: Item, extracted: ExtractedText) -> None:
        path = self._cache_path(item)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(extracted.model_dump_json(), encoding="utf-8")


def _capped(extracted: ExtractedText, max_chars: int) -> ExtractedText:
    return extracted.model_copy(update={"text": clean_text(extracted.text, max_chars)})


def _fallback(item: Item, errors: tuple[str, ...]) -> ExtractedText:
    if item.summary:
        return ExtractedText(
            text=item.summary, source="abstract", links=collect_links(item.summary), errors=errors
        )
    return ExtractedText(text=item.title, source="title", errors=errors)

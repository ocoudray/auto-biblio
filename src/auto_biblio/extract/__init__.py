"""Full-text extraction for deep analyses."""

import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.kb.notes import SourceText
from auto_biblio.domain.models import Item

_BACK_MATTER = re.compile(
    r"^\s*(?:#+\s*)?(?:[0-9IVX]+\.?\s+)?"
    r"(?:references|bibliography|acknowledge?ments?|appendix|appendices)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)
_URL = re.compile(r"https?://[^\s)\]>\"'<]+")


class ExtractedText(BaseModel):
    """The text an analysis is written from."""

    model_config = ConfigDict(frozen=True)

    text: str
    source: SourceText
    links: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    """Why richer sources were not used, when the text is a fallback."""


class TextExtractor(Protocol):
    """Finds the best available text for an item."""

    def extract(self, item: Item, max_chars: int) -> ExtractedText:
        """Extract the text of an item, falling back to its summary.

        Args:
            item: The item.
            max_chars: Size cap of the text.

        Returns:
            The text, its source and the links it contains.
        """
        ...


def clean_text(text: str, max_chars: int) -> str:
    """Drop back matter (references, appendices) and cap the size.

    Args:
        text: The extracted text.
        max_chars: Size cap.

    Returns:
        The text before the first back-matter heading, cut at a word boundary.
    """
    match = _BACK_MATTER.search(text)
    kept = text[: match.start()] if match else text
    kept = kept.strip()
    if len(kept) <= max_chars:
        return kept
    cut = kept[:max_chars]
    space = cut.rfind(" ")
    return (cut[:space] if space > max_chars // 2 else cut).rstrip()


def collect_links(text: str) -> tuple[str, ...]:
    """List the URLs of a text.

    Args:
        text: Any text.

    Returns:
        Unique URLs, trailing punctuation removed, sorted.
    """
    return tuple(sorted({url.rstrip(".,;:") for url in _URL.findall(text)}))

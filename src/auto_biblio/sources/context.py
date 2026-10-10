"""Short context for items without summary: README, model card or page description."""

import logging
import re
from collections.abc import Sequence
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from auto_biblio.domain.errors import ContextFetchError, SourceUnavailableError
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.models import Item
from auto_biblio.sources._http import get

logger = logging.getLogger(__name__)

_SOURCE = "context"
_HF_MODEL = re.compile(r"^/([\w.-]+)/([\w.-]+)/?$")
_MARKDOWN_NOISE = (
    (re.compile(r"```.*?```", re.DOTALL), " "),
    (re.compile(r"<[^>]+>"), " "),
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), " "),
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),
    (re.compile(r"^\s*#+\s*", re.MULTILINE), ""),
    (re.compile(r"[*_`>|]"), " "),
)
_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


class _MetaDescription(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.og: str | None = None
        self.plain: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        values = dict(attrs)
        content = values.get("content")
        if values.get("property") == "og:description" and content:
            self.og = content
        elif values.get("name") == "description" and content:
            self.plain = content


class ContextFetcher:
    """Fetches a few words describing an item, without any LLM."""

    def __init__(
        self, client: httpx.Client, max_words: int, github_token: SecretStr | None = None
    ) -> None:
        """Build the fetcher.

        Args:
            client: Injected HTTP client.
            max_words: Length cap of a snippet.
            github_token: Raises GitHub's rate limit for README requests.
        """
        self._client = client
        self._max_words = max_words
        self._github_token = github_token

    def fetch(self, item: Item) -> str:
        """Fetch the context snippet of an item.

        Args:
            item: An item without summary.

        Returns:
            At most `max_words` words.

        Raises:
            ContextFetchError: If nothing usable could be fetched.
        """
        url = str(item.url)
        try:
            text = self._raw_text(item, url)
        except SourceUnavailableError as exc:
            raise ContextFetchError(url, str(exc)) from exc
        words = text.split()
        if not words:
            raise ContextFetchError(url, "no description found")
        return " ".join(words[: self._max_words])

    def fetch_many(self, items: Sequence[Item]) -> dict[ItemId, str]:
        """Fetch snippets, skipping the items whose fetch fails.

        Args:
            items: Items without summary.

        Returns:
            The snippet of each item that got one.
        """
        snippets: dict[ItemId, str] = {}
        for item in items:
            try:
                snippets[item.id] = self.fetch(item)
            except ContextFetchError as exc:
                logger.warning("no context for %s: %s", item.id, exc)
        return snippets

    def _raw_text(self, item: Item, url: str) -> str:
        if item.id.startswith("gh:") and "@" not in item.id:
            return _strip_markdown(self._readme(item.id.removeprefix("gh:")))
        parts = urlsplit(url)
        model = _HF_MODEL.match(parts.path)
        if parts.netloc.removeprefix("www.") == "huggingface.co" and model and model[1] != "papers":
            card_url = f"https://huggingface.co/{model[1]}/{model[2]}/raw/main/README.md"
            card = get(self._client, card_url, source=_SOURCE).text
            return _strip_markdown(_FRONT_MATTER.sub("", card))
        return _page_description(get(self._client, url, source=_SOURCE).text)

    def _readme(self, repo: str) -> str:
        headers = {"Accept": "application/vnd.github.raw"}
        if self._github_token is not None:
            headers["Authorization"] = f"Bearer {self._github_token.get_secret_value()}"
        url = f"https://api.github.com/repos/{repo}/readme"
        return get(self._client, url, source=_SOURCE, headers=headers).text


def _strip_markdown(text: str) -> str:
    for pattern, replacement in _MARKDOWN_NOISE:
        text = pattern.sub(replacement, text)
    return text


def _page_description(html: str) -> str:
    parser = _MetaDescription()
    parser.feed(html)
    return parser.og or parser.plain or ""

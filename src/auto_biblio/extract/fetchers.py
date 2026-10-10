"""Fetchers of full text: arXiv (HTML then PDF), GitHub repositories and web articles."""

import io
from collections.abc import Mapping
from typing import cast

import httpx
import trafilatura
from pydantic import SecretStr
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from auto_biblio.domain.errors import ExtractionError, SourceUnavailableError
from auto_biblio.sources._http import Throttle, get

MIN_ARTICLE_CHARS = 200
"""Below this, an extracted page is considered empty (a cookie wall, a login page)."""
MAX_PDF_PAGES = 40
HTTP_NOT_FOUND = 404
_SOURCE = "extract"


def _fetch(
    client: httpx.Client, url: str, headers: Mapping[str, str] | None = None
) -> httpx.Response:
    try:
        return get(client, url, source=_SOURCE, headers=headers)
    except SourceUnavailableError as exc:
        raise ExtractionError(url, str(exc)) from exc


def html_to_text(html: str, url: str) -> str:
    """Extract the main content of a page as Markdown.

    Args:
        html: The page.
        url: Its URL, for errors.

    Returns:
        The main content.

    Raises:
        ExtractionError: If the page has no substantial content.
    """
    text = trafilatura.extract(html, output_format="markdown", include_links=True)
    if text is None or len(text) < MIN_ARTICLE_CHARS:
        raise ExtractionError(url, "no main content found")
    return text


class ArxivFetcher:
    """Full text of an arXiv paper: the HTML rendering, else the PDF."""

    def __init__(self, client: httpx.Client, throttle: Throttle) -> None:
        """Build the fetcher.

        Args:
            client: Injected HTTP client.
            throttle: arXiv asks for 3 s between requests.
        """
        self._client = client
        self._throttle = throttle

    def fetch(self, arxiv_id: str) -> str:
        """Fetch the full text of a paper.

        Args:
            arxiv_id: The identifier, without prefix.

        Returns:
            The text.

        Raises:
            ExtractionError: If neither the HTML nor the PDF gives text.
        """
        try:
            self._throttle.wait()
            html = _fetch(self._client, f"https://arxiv.org/html/{arxiv_id}").text
            return html_to_text(html, arxiv_id)
        except ExtractionError as html_error:
            try:
                return self._pdf(arxiv_id)
            except ExtractionError as pdf_error:
                msg = f"HTML: {html_error}; PDF: {pdf_error}"
                source = f"arxiv:{arxiv_id}"
                raise ExtractionError(source, msg) from pdf_error

    def _pdf(self, arxiv_id: str) -> str:
        url = f"https://arxiv.org/pdf/{arxiv_id}"
        self._throttle.wait()
        content = _fetch(self._client, url).content
        try:
            reader = PdfReader(io.BytesIO(content))
            text = "\n".join(page.extract_text() for page in reader.pages[:MAX_PDF_PAGES])
        except (PyPdfError, ValueError) as exc:
            raise ExtractionError(url, f"unreadable PDF: {exc}") from exc
        if not text.strip():
            raise ExtractionError(url, "PDF without text")
        return text


class RepoFetcher:
    """README and latest release notes of a GitHub repository."""

    def __init__(self, client: httpx.Client, token: SecretStr | None) -> None:
        """Build the fetcher.

        Args:
            client: Injected HTTP client.
            token: Optional GitHub token (raises the rate limit).
        """
        self._client = client
        self._headers = {"Accept": "application/vnd.github.raw"}
        if token is not None:
            self._headers["Authorization"] = f"Bearer {token.get_secret_value()}"

    def fetch(self, repo: str) -> str:
        """Fetch the README, followed by the latest release notes when there are some.

        Args:
            repo: `owner/repo`.

        Returns:
            The text.

        Raises:
            ExtractionError: If the README cannot be fetched or is empty.
        """
        base = f"https://api.github.com/repos/{repo}"
        readme = _fetch(self._client, f"{base}/readme", headers=self._headers).text
        if not readme.strip():
            raise ExtractionError(base, "empty README")
        return readme + self._latest_release(base)

    def _latest_release(self, base: str) -> str:
        headers = {**self._headers, "Accept": "application/vnd.github+json"}
        try:
            data: object = _fetch(self._client, f"{base}/releases/latest", headers=headers).json()
        except (ExtractionError, ValueError):
            return ""  # no release, or no JSON: the README alone is fine
        if not isinstance(data, dict):
            return ""
        release = cast("dict[str, object]", data)  # a JSON object from the GitHub API
        body, tag = release.get("body"), release.get("tag_name")
        if not isinstance(body, str) or not body.strip():
            return ""
        return f"\n\n## Latest release {tag}\n\n{body}"


class ArticleFetcher:
    """Main content of a web page (blog post, newsletter issue)."""

    def __init__(self, client: httpx.Client) -> None:
        """Build the fetcher.

        Args:
            client: Injected HTTP client (following redirects).
        """
        self._client = client

    def fetch(self, url: str) -> str:
        """Fetch the main content of a page.

        Args:
            url: The page.

        Returns:
            The text.

        Raises:
            ExtractionError: If the page cannot be fetched or has no main content.
        """
        return html_to_text(_fetch(self._client, url).text, url)

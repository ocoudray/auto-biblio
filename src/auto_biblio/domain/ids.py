"""Canonical identities: map every URL pointing at the same content to one `ItemId`."""

import hashlib
import re
from typing import Literal, NewType
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ItemId = NewType("ItemId", str)
ItemKind = Literal["paper", "repo", "release", "blog_post", "discussion"]

_TRACKING_PARAMS = frozenset({"ref", "source"})
_ARXIV_HOSTS = frozenset({"arxiv.org", "export.arxiv.org"})
_ARXIV_PATH = re.compile(r"^/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?$")
_HF_PAPER_PATH = re.compile(r"^/papers/(\d{4}\.\d{4,5})$")
_GITHUB_RELEASE = re.compile(r"^/([\w.-]+)/([\w.-]+)/releases/tag/([^/]+)$")
_GITHUB_REPO = re.compile(r"^/([\w.-]+)/([\w.-]+)(?:/.*)?$")
# Top-level github.com pages that look like "/owner/repo" but are not repositories.
_GITHUB_RESERVED = frozenset(
    {"features", "topics", "orgs", "settings", "marketplace", "sponsors", "collections"}
)


def normalize_url(url: str) -> str:
    """Normalize a URL so that trivially different spellings compare equal.

    Forces ``https``, lowercases the host, drops ``www.``, tracking parameters
    (``utm_*``, ``ref``, ``source``), the fragment and the trailing slash, and
    sorts the remaining query parameters.

    Args:
        url: Any absolute URL.

    Returns:
        The normalized URL.
    """
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.startswith("utm_") and key not in _TRACKING_PARAMS
    )
    return urlunsplit(("https", host, path, urlencode(query), ""))


def canonical_id(url: str) -> ItemId:
    """Compute the canonical identity of the content a URL points at.

    Args:
        url: Any absolute URL (arXiv, Hugging Face paper, GitHub, DOI, or other).

    Returns:
        ``arxiv:<id>``, ``gh:<owner>/<repo>``, ``gh:<owner>/<repo>@<tag>``,
        ``doi:<doi>`` or ``url:<hash>``.
    """
    normalized = normalize_url(url)
    parts = urlsplit(normalized)
    host, path = parts.netloc, parts.path
    known = _known_id(host, path)
    if known is not None:
        return known
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return ItemId(f"url:{digest}")


def _known_id(host: str, path: str) -> ItemId | None:
    if host in _ARXIV_HOSTS and (match := _ARXIV_PATH.match(path)):
        return ItemId(f"arxiv:{match.group(1)}")
    if host == "huggingface.co" and (match := _HF_PAPER_PATH.match(path)):
        return ItemId(f"arxiv:{match.group(1)}")
    if host == "doi.org" and len(path) > 1:
        return ItemId(f"doi:{path[1:].lower()}")
    if host == "github.com":
        return _github_id(path)
    return None


def _github_id(path: str) -> ItemId | None:
    if match := _GITHUB_RELEASE.match(path):
        owner, repo, tag = match.groups()
        return ItemId(f"gh:{owner.lower()}/{repo.lower()}@{tag}")
    match = _GITHUB_REPO.match(path)
    if match is None or match.group(1).lower() in _GITHUB_RESERVED:
        return None
    owner, repo = match.groups()
    return ItemId(f"gh:{owner.lower()}/{repo.lower()}")


def kind_for(item_id: ItemId, default: ItemKind) -> ItemKind:
    """Infer the kind of an item from its canonical identity.

    Args:
        item_id: Canonical identity.
        default: Kind to use when the identity does not tell (``url:`` ids).

    Returns:
        The inferred kind.
    """
    namespace, _, rest = item_id.partition(":")
    if namespace in {"arxiv", "doi"}:
        return "paper"
    if namespace == "gh":
        return "release" if "@" in rest else "repo"
    return default

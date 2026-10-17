"""`wiki check`: the structural rules every wiki page must follow (spec §5)."""

import posixpath
import re
from collections.abc import Iterator
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.wiki.pages import INDEX, Notion, Wiki

REFERENCES = "Références fondatrices"
_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s#]+\.md)(?:#[^)]*)?\)")
_CAPTION_MARKERS = ("Figure originale", "Source :")


class Problem(BaseModel):
    """One rule a wiki file breaks."""

    model_config = ConfigDict(frozen=True)

    origin: str
    """File, relative to `wiki/`."""
    message: str

    def __str__(self) -> str:
        """Render as `<origin>: <message>`."""
        return f"{self.origin}: {self.message}"


def _file(notion_id: str) -> str:
    return f"{notion_id}.md"


def check_wiki(wiki: Wiki, themes: frozenset[str]) -> tuple[Problem, ...]:
    """Check the structure of the wiki.

    Args:
        wiki: The wiki as read from `wiki/`.
        themes: Theme ids of the profile.

    Returns:
        Every problem, sorted by file then message.
    """
    found = [
        *(
            Problem(origin=p.as_posix(), message=f"unreadable: {r}")
            for p, r in wiki.unreadable.items()
        ),
        *_check_domains(wiki),
        *_check_cycles(wiki),
    ]
    for notion in wiki.notions.values():
        found.extend(_check_notion(notion, wiki, themes))
    return tuple(sorted(found, key=lambda p: (p.origin, p.message)))


def _planned(wiki: Wiki) -> frozenset[str]:
    return frozenset(n for d in wiki.domains.values() for n in d.index.order)


def _check_domains(wiki: Wiki) -> Iterator[Problem]:
    for domain in wiki.domains.values():
        for entry in domain.index.order:
            if not entry.startswith(f"{domain.id}/"):
                message = f"order entry {entry} is not in domain {domain.id}"
                yield Problem(origin=f"{domain.id}/{INDEX}", message=message)


def _check_notion(notion: Notion, wiki: Wiki, themes: frozenset[str]) -> Iterator[Problem]:
    origin = _file(notion.id)
    known = _planned(wiki) | frozenset(wiki.notions)
    meta = notion.meta
    yield from (
        Problem(origin=origin, message=f"unknown prerequisite {n}")
        for n in meta.prerequisites
        if n not in known
    )
    yield from (
        Problem(origin=origin, message=f"unknown related notion {n}")
        for n in meta.related
        if n not in known
    )
    yield from (
        Problem(origin=origin, message=f"unknown theme {t}") for t in meta.themes if t not in themes
    )
    if not notion.summary:
        yield Problem(origin=origin, message="missing summary under the title")
    if REFERENCES not in notion.headings:
        yield Problem(origin=origin, message=f"missing section ## {REFERENCES}")
    domain_id = notion.id.split("/", 1)[0]
    domain = wiki.domains.get(domain_id)
    if domain is None:
        yield Problem(origin=origin, message=f"domain {domain_id} has no {INDEX}")
    elif notion.id not in domain.index.order:
        yield Problem(origin=origin, message=f"not listed in {domain_id}/{INDEX} order")
    yield from _check_images(notion, wiki, origin)
    yield from _check_links(notion, wiki, origin)


def _resolve(notion: Notion, target: str) -> str | None:
    # Paths are relative to the notion's folder; None when they leave the wiki.
    folder = notion.id.split("/", 1)[0]
    resolved = posixpath.normpath(posixpath.join(folder, target))
    return None if resolved.startswith("..") else resolved


def _check_images(notion: Notion, wiki: Wiki, origin: str) -> Iterator[Problem]:
    lines = notion.body.split("\n")
    for index, line in enumerate(lines):
        for target in _IMAGE.findall(line):
            following = next((ln.strip() for ln in lines[index + 1 :] if ln.strip()), "")
            captioned = following.startswith("*") and any(m in following for m in _CAPTION_MARKERS)
            if not captioned:
                yield Problem(origin=origin, message=f"image {target} has no provenance caption")
            if "://" in target:
                continue
            resolved = _resolve(notion, target)
            if resolved is None or PurePosixPath(resolved) not in wiki.assets:
                yield Problem(origin=origin, message=f"missing image {target}")


def _check_links(notion: Notion, wiki: Wiki, origin: str) -> Iterator[Problem]:
    pages = {_file(n) for n in wiki.notions} | {f"{d}/{INDEX}" for d in wiki.domains}
    for target in _LINK.findall(notion.body):
        if "://" in target:
            continue
        resolved = _resolve(notion, target)
        if resolved is not None and resolved not in pages:
            yield Problem(origin=origin, message=f"broken link {target}")


def _check_cycles(wiki: Wiki) -> Iterator[Problem]:
    graph = {
        n: [p for p in wiki.notions[n].meta.prerequisites if p in wiki.notions]
        for n in wiki.notions
    }
    reported: set[frozenset[str]] = set()
    for start in sorted(graph):
        for cycle in _cycles_from(start, graph):
            key = frozenset(cycle)
            if key in reported:
                continue
            reported.add(key)
            first = min(cycle)
            rotated = cycle[cycle.index(first) :] + cycle[: cycle.index(first)]
            path = " → ".join([*rotated, first])
            yield Problem(origin=_file(first), message=f"prerequisite cycle: {path}")


def _cycles_from(start: str, graph: dict[str, list[str]]) -> Iterator[list[str]]:
    stack: list[tuple[str, list[str]]] = [(start, [start])]
    while stack:
        node, path = stack.pop()
        for nxt in graph[node]:
            if nxt == start:
                yield path
            elif nxt not in path:
                stack.append((nxt, [*path, nxt]))

"""`wiki check`: the structural rules every wiki page must follow (spec §5)."""

import posixpath
import re
from collections import deque
from collections.abc import Iterator
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.wiki.pages import INDEX, Notion, Wiki

REFERENCES = "Références fondatrices"
_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s#]+\.(?:md|ipynb))(?:#[^)]*)?\)")
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
    assets = wiki.assets
    for target in _LINK.findall(notion.body):
        if "://" in target:
            continue
        resolved = _resolve(notion, target)
        if resolved is not None and resolved not in pages and PurePosixPath(resolved) not in assets:
            yield Problem(origin=origin, message=f"broken link {target}")


def _check_cycles(wiki: Wiki) -> Iterator[Problem]:
    graph = {
        n: [p for p in wiki.notions[n].meta.prerequisites if p in wiki.notions]
        for n in sorted(wiki.notions)
    }
    # One problem per strongly connected component: linear, whatever the number of cycles.
    for component in _Tarjan(graph).components:
        first = min(component)
        if len(component) == 1 and first not in graph[first]:
            continue
        path = " → ".join([*_cycle_through(first, graph, component), first])
        yield Problem(origin=_file(first), message=f"prerequisite cycle: {path}")


class _Tarjan:
    """Strongly connected components (iterative Tarjan), so deep graphs never recurse."""

    def __init__(self, graph: dict[str, list[str]]) -> None:
        self._graph = graph
        self._index: dict[str, int] = {}
        self._low: dict[str, int] = {}
        self._stack: list[str] = []
        self._on_stack: set[str] = set()
        self.components: list[set[str]] = []
        for root in graph:
            if root not in self._index:
                self._visit(root)

    def _visit(self, root: str) -> None:
        work = [(root, 0)]
        while work:
            node, i = work.pop()
            if i == 0:
                self._index[node] = self._low[node] = len(self._index)
                self._stack.append(node)
                self._on_stack.add(node)
            if i < len(self._graph[node]):
                work.append((node, i + 1))
                nxt = self._graph[node][i]
                if nxt not in self._index:
                    work.append((nxt, 0))
                elif nxt in self._on_stack:
                    self._low[node] = min(self._low[node], self._index[nxt])
                continue
            if work:  # back in the parent, which sits right under the finished node
                parent = work[-1][0]
                self._low[parent] = min(self._low[parent], self._low[node])
            if self._low[node] == self._index[node]:
                self._close(node)

    def _close(self, node: str) -> None:
        component: set[str] = set()
        while True:
            member = self._stack.pop()
            self._on_stack.discard(member)
            component.add(member)
            if member == node:
                break
        self.components.append(component)


def _cycle_through(first: str, graph: dict[str, list[str]], component: set[str]) -> list[str]:
    """Shortest cycle from `first` back to itself, inside its component (breadth first)."""
    previous: dict[str, str] = {}
    queue = deque([first])
    while queue:
        node = queue.popleft()
        for nxt in graph[node]:
            if nxt == first:
                path = [node]
                while path[-1] != first:
                    path.append(previous[path[-1]])
                return path[::-1]
            if nxt in component and nxt not in previous:
                previous[nxt] = node
                queue.append(nxt)
    return [first]  # unreachable: every node of a component lies on a cycle through `first`

"""Read the wiki of a data repository (`wiki/`) and the state of `wiki link` (`state/wiki/`)."""

from pathlib import Path, PurePosixPath

from pydantic import TypeAdapter

from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.wiki.links import Candidate, NoteLinks, WikiLinks
from auto_biblio.store._files import atomic_write_text

FIGURE_SUFFIXES = frozenset({".svg", ".png"})
_NOTES = TypeAdapter(dict[ItemId, NoteLinks])
_CANDIDATES = TypeAdapter(dict[str, Candidate])


class WikiStore:
    """The `wiki/` directory of a data repository."""

    def __init__(self, data_dir: Path) -> None:
        """Wrap a data repository.

        Args:
            data_dir: Root of the data repository.
        """
        self._root = data_dir / "wiki"
        self._state = data_dir / "state" / "wiki"

    def exists(self) -> bool:
        """Whether the repository has a wiki."""
        return self._root.is_dir()

    def files(self) -> dict[PurePosixPath, str]:
        """Return every Markdown file of the wiki.

        Returns:
            Contents by path relative to `wiki/`.
        """
        if not self.exists():
            return {}
        return {
            PurePosixPath(path.relative_to(self._root).as_posix()): path.read_text(encoding="utf-8")
            for path in sorted(self._root.rglob("*.md"))
        }

    def assets(self) -> dict[PurePosixPath, bytes]:
        """Return the published files of the wiki: figures and notebooks.

        Figures are `<domain>/img/*.svg|png`, notebooks `<domain>/code/*.ipynb`.

        Returns:
            Contents by path relative to `wiki/`.
        """
        if not self.exists():
            return {}
        figures = (p for p in self._root.glob("*/img/*") if p.suffix in FIGURE_SUFFIXES)
        return {
            PurePosixPath(path.relative_to(self._root).as_posix()): path.read_bytes()
            for path in sorted((*figures, *self._root.glob("*/code/*.ipynb")))
        }

    def read_links(self) -> WikiLinks:
        """Read what `wiki link` knows.

        Returns:
            The links and candidates; empty when nothing was written yet.
        """
        links, candidates = self._state / "links.json", self._state / "candidates.json"
        return WikiLinks(
            notes=_NOTES.validate_json(links.read_bytes()) if links.exists() else {},
            candidates=(
                _CANDIDATES.validate_json(candidates.read_bytes()) if candidates.exists() else {}
            ),
        )

    def write_links(self, links: WikiLinks) -> Path:
        """Write the links (`links.json`) and the candidates (`candidates.json`).

        Args:
            links: What `wiki link` knows.

        Returns:
            The `state/wiki/` directory.
        """
        notes = dict(sorted(links.notes.items()))
        candidates = dict(sorted(links.candidates.items()))
        atomic_write_text(
            self._state / "links.json", _NOTES.dump_json(notes, indent=1).decode() + "\n"
        )
        atomic_write_text(
            self._state / "candidates.json",
            _CANDIDATES.dump_json(candidates, indent=1).decode() + "\n",
        )
        return self._state

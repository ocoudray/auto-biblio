"""Read the wiki of a data repository (`wiki/`)."""

from pathlib import Path, PurePosixPath

FIGURE_SUFFIXES = frozenset({".svg", ".png"})


class WikiStore:
    """The `wiki/` directory of a data repository."""

    def __init__(self, data_dir: Path) -> None:
        """Wrap a data repository.

        Args:
            data_dir: Root of the data repository.
        """
        self._root = data_dir / "wiki"

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
        """Return the figures of the wiki (`<domain>/img/*.svg|png`).

        Returns:
            Contents by path relative to `wiki/`.
        """
        if not self.exists():
            return {}
        return {
            PurePosixPath(path.relative_to(self._root).as_posix()): path.read_bytes()
            for path in sorted(self._root.glob("*/img/*"))
            if path.suffix in FIGURE_SUFFIXES
        }

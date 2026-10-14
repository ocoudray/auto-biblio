"""Knowledge base store: Markdown notes, theme pages and changelogs under `kb/`."""

import logging
from pathlib import Path, PurePosixPath
from typing import Self

from auto_biblio.domain.errors import KBFormatError
from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.changelog import ChangelogEntry, render_changelog
from auto_biblio.domain.kb.notes import Note, parse_note, render_note
from auto_biblio.domain.kb.pages import ThemePage, parse_theme_page, render_theme_page
from auto_biblio.store._files import atomic_write_text

logger = logging.getLogger(__name__)


class KBStore:
    """Reads and writes the knowledge base of a data repository."""

    def __init__(self, root: Path, notes: dict[ItemId, Note], broken: set[Path]) -> None:
        """Wrap already-loaded notes; use `KBStore.open` instead.

        Args:
            root: The `kb/` directory.
            notes: Loaded notes by id.
            broken: Note files that could not be read back.
        """
        self._root = root
        self._notes = notes
        self._broken = broken

    @classmethod
    def open(cls, root: Path) -> Self:
        """Load every note under `root`.

        An unreadable note is skipped with a warning, and protected from being overwritten.

        Args:
            root: The `kb/` directory.

        Returns:
            The store.
        """
        notes: dict[ItemId, Note] = {}
        broken: set[Path] = set()
        for path in sorted((root / "notes").glob("*/*.md")):
            origin = path.relative_to(root).as_posix()
            try:
                note = parse_note(path.read_text(encoding="utf-8"), origin)
            except KBFormatError as exc:
                logger.warning("skipping unreadable note: %s", exc)
                broken.add(path)
                continue
            notes[note.meta.id] = note
        return cls(root, notes, broken)

    def get(self, note_id: ItemId) -> Note | None:
        """Return a note.

        Args:
            note_id: The note id.

        Returns:
            The note, if it exists.
        """
        return self._notes.get(note_id)

    def all_notes(self) -> tuple[Note, ...]:
        """Return every note, sorted by id.

        Returns:
            The notes.
        """
        return tuple(self._notes[i] for i in sorted(self._notes))

    def notes_for_theme(self, theme: ThemeId) -> tuple[Note, ...]:
        """Return the notes attached to a theme.

        Args:
            theme: The theme.

        Returns:
            The notes, sorted by id.
        """
        return tuple(n for n in self.all_notes() if theme in n.meta.themes)

    def note_paths(self) -> dict[ItemId, PurePosixPath]:
        """Locate every note.

        Returns:
            The path of each note, relative to `kb/`.
        """
        return {note_id: note.path for note_id, note in self._notes.items()}

    def files(self) -> dict[PurePosixPath, str]:
        """Return the content of every page source of the knowledge base.

        Returns:
            The notes, theme pages and changelogs, by path relative to `kb/`.
        """
        found: dict[PurePosixPath, str] = {}
        for pattern in ("notes/*/*.md", "themes/*.md", "changelog/*.md"):
            for path in sorted(self._root.glob(pattern)):
                relative = PurePosixPath(path.relative_to(self._root).as_posix())
                found[relative] = path.read_text(encoding="utf-8")
        return found

    def write_note(self, note: Note) -> Path:
        """Write a note.

        Args:
            note: The note.

        Returns:
            The written file.

        Raises:
            KBFormatError: If the existing file could not be read back (it is left untouched,
                so that hand-written notes are never lost).
        """
        path = self._root / note.path
        if path in self._broken:
            raise KBFormatError(note.path.as_posix(), "unreadable file left untouched")
        atomic_write_text(path, render_note(note))
        self._notes[note.meta.id] = note
        return path

    def read_theme(self, theme: ThemeId) -> ThemePage | None:
        """Read a theme page.

        Args:
            theme: The theme.

        Returns:
            The page, if it exists and can be read back.
        """
        path = self._root / "themes" / f"{theme}.md"
        if not path.exists():
            return None
        try:
            return parse_theme_page(path.read_text(encoding="utf-8"), f"themes/{theme}.md")
        except KBFormatError as exc:
            logger.warning("ignoring unreadable theme page: %s", exc)
            return None

    def write_theme(self, page: ThemePage) -> Path:
        """Write a theme page, linking reference tools to their notes.

        Args:
            page: The page.

        Returns:
            The written file.
        """
        path = self._root / page.path
        atomic_write_text(path, render_theme_page(page, self.note_paths()))
        return path

    def write_changelog(self, entry: ChangelogEntry) -> Path:
        """Write the changelog of a week.

        Args:
            entry: The changelog.

        Returns:
            The written file.
        """
        path = self._root / "changelog" / f"{entry.week}.md"
        atomic_write_text(path, render_changelog(entry))
        return path

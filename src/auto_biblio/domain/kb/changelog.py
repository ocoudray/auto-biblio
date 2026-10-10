"""Weekly changelog of the knowledge base."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from auto_biblio.domain.features import ThemeId
from auto_biblio.domain.ids import ItemId
from auto_biblio.domain.kb.markdown import clean
from auto_biblio.domain.kb.notes import Depth, NoteKind, SourceText
from auto_biblio.domain.kb.pages import RemovedLink

NoteChangeKind = Literal["created", "deepened", "refreshed"]

_VERB: dict[NoteChangeKind, str] = {
    "created": "créée",
    "deepened": "approfondie",
    "refreshed": "réécrite",
}


class NoteChange(BaseModel):
    """A note written this week."""

    model_config = ConfigDict(frozen=True)

    note_id: ItemId
    title: str
    kind: NoteKind
    change: NoteChangeKind
    depth: Depth
    source_text: SourceText


class ChangelogEntry(BaseModel):
    """Everything the knowledge base gained or lost in one week."""

    model_config = ConfigDict(frozen=True)

    week: str
    notes: tuple[NoteChange, ...] = ()
    theme: ThemeId | None = None
    links_added: tuple[str, ...] = ()
    links_removed: tuple[RemovedLink, ...] = ()
    degradations: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """Whether nothing changed."""
        return not (self.notes or self.theme or self.links_removed)


def render_changelog(entry: ChangelogEntry) -> str:
    """Render the changelog of a week to Markdown.

    Args:
        entry: The changelog.

    Returns:
        The file content.
    """
    lines = [f"# Évolutions de la base — {entry.week}", ""]
    lines.append("## Fiches")
    lines.append("")
    if entry.notes:
        lines.extend(
            f"- {clean(n.title)} (`{n.note_id}`) : fiche {_VERB[n.change]}, {n.depth}, "
            f"lue depuis {n.source_text}"
            for n in entry.notes
        )
    else:
        lines.append("Aucune fiche cette semaine.")
    lines.extend(["", "## Page thème", ""])
    lines.append(f"Page `{entry.theme}` réécrite." if entry.theme else "Aucune page réécrite.")
    if entry.links_added:
        lines.extend(["", "## Liens ajoutés", ""])
        lines.extend(f"- {url}" for url in entry.links_added)
    if entry.links_removed:
        lines.extend(["", "## Liens retirés", ""])
        lines.extend(f"- {r.url} : {clean(r.reason)}" for r in entry.links_removed)
    if entry.degradations:
        lines.extend(["", "## Dégradations", ""])
        lines.extend(f"- {d}" for d in entry.degradations)
    return "\n".join(lines) + "\n"

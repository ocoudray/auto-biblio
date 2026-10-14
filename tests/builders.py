"""Builders for domain objects used across test modules."""

from collections.abc import Mapping
from datetime import UTC, date, datetime

from auto_biblio.domain.features import FeatureVector, ThemeId
from auto_biblio.domain.ids import ItemId, ItemKind
from auto_biblio.domain.kb.notes import DeepAnalysis, Note, NoteMeta, ShortNote
from auto_biblio.domain.kb.pages import ThemePage, ThemePageContent, ThemePageMeta
from auto_biblio.domain.models import Item, Sighting, Signal, SignalKind, SourceType
from auto_biblio.domain.triage import ScoredItem, ScoringReport, TriageRun, TriageVerdict

NOW = datetime(2026, 10, 10, 5, 0, tzinfo=UTC)


def make_item(  # noqa: PLR0913 - builder mirrors the model's fields
    *,
    item_id: str = "arxiv:2410.12345",
    source_type: SourceType = "arxiv",
    source: str | None = None,
    title: str = "Title",
    summary: str | None = "summary",
    seen_at: datetime = NOW,
    links: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    kind: ItemKind = "paper",
) -> Item:
    """Build an item seen once by one source."""
    return Item(
        id=ItemId(item_id),
        kind=kind,
        title=title,
        summary=summary,
        url="https://example.com/x",  # pyright: ignore[reportArgumentType] - validated to HttpUrl
        authors=("A",),
        published_at=None,
        first_seen=seen_at,
        sightings=(
            Sighting(
                source=source or source_type,
                source_type=source_type,
                seen_at=seen_at,
                origin_url=f"https://{source_type}.example/x",
            ),
        ),
        links=tuple(ItemId(link) for link in links),
        tags=tags,
    )


def make_signal(
    *,
    item_id: str = "gh:o/r",
    kind: SignalKind = "gh_stars",
    value: int = 10,
    observed_at: datetime = NOW,
) -> Signal:
    """Build a signal."""
    return Signal(
        item_id=ItemId(item_id), kind=kind, value=value, observed_at=observed_at, source="s"
    )


def make_features(item_id: str = "arxiv:2410.12345", **overrides: object) -> FeatureVector:
    """Build a feature vector (paper, abstract, mid-range scores)."""
    base: dict[str, object] = {
        "item_id": item_id,
        "family": "paper",
        "context_level": "abstract",
        "theme_similarity": {},
        "theme_percentile": {"agentic": 0.9},
        "relevance": 0.9,
        "popularity": 0.5,
        "source_count": 1,
        "watched": False,
        "revenant": False,
        "age_days": 1.0,
    }
    return FeatureVector.model_validate(base | overrides)


def make_run(week: str, items: tuple[ScoredItem, ...], generated_at: datetime = NOW) -> TriageRun:
    """Build a triage journal."""
    return TriageRun(
        week=week,
        run_id=f"{week}-triage",
        generated_at=generated_at,
        scoring=ScoringReport(version="fixed-v1"),
        items=items,
    )


def make_verdict(
    ref: str = "i01",
    scores: Mapping[ThemeId, int] | Mapping[str, int] | None = None,
    **overrides: object,
) -> TriageVerdict:
    """Build a triage verdict from a {theme: score} mapping."""
    base: dict[str, object] = {
        "ref": ref,
        "relevance": scores if scores is not None else {"agentic": 4},
        "item_type": "tool",
        "novelty": "high",
        "confidence": "medium",
        "reason": "Short reason.",
    }
    return TriageVerdict.model_validate(base | overrides)


def make_note(  # noqa: PLR0913 - builder mirrors the note's main fields
    note_id: str = "arxiv:2410.12345",
    *,
    depth: str = "short",
    analyzed_at: date = date(2026, 10, 11),
    links: tuple[str, ...] = (),
    themes: tuple[str, ...] = ("agentic",),
    my_notes: str = "",
) -> Note:
    """Build a note (short content, or a deep one when `depth="deep"`)."""
    short = {"summary": f"About {note_id}.", "contribution": "New.", "relevance": "Useful."}
    content: ShortNote | DeepAnalysis = (
        DeepAnalysis.model_validate(
            short
            | {
                "problem": "P.",
                "method": ["Step"],
                "results": [],
                "limitations": [],
                "positioning": "Pos.",
                "takeaways": ["Do it"],
                "further_reading": [],
                "verdict": "Worth it.",
                "confidence": "high",
            }
        )
        if depth == "deep"
        else ShortNote.model_validate(short)
    )
    meta = NoteMeta.model_validate(
        {
            "id": note_id,
            "kind": "paper",
            "title": f"Title {note_id}",
            "url": "https://example.com/x",
            "themes": list(themes),
            "links": list(links),
            "depth": depth,
            "source_text": "full_text" if depth == "deep" else "abstract",
            "first_seen": date(2026, 10, 1),
            "analyzed_at": analyzed_at,
            "model_id": "m",
            "prompt_version": "deep_analysis_v1" if depth == "deep" else "short_note_v1",
        }
    )
    return Note(meta=meta, content=content, my_notes=my_notes)


def make_theme_page(
    theme: str = "agentic", *, notes: tuple[str, ...] = (), updated_at: date = date(2026, 10, 13)
) -> ThemePage:
    """Build a theme page citing the given notes."""
    content = ThemePageContent(
        overview="State of the art.",
        key_concepts=("Tool use",),
        dominant_approaches=("ReAct",),
        reference_tools=(),
        open_questions=("Evaluation?",),
        further_reading=(),
    )
    meta = ThemePageMeta.model_validate(
        {
            "theme": theme,
            "label": theme.title(),
            "updated_at": updated_at,
            "prompt_version": "theme_page_v1",
            "model_id": "m",
            "notes": list(notes),
        }
    )
    return ThemePage(meta=meta, content=content)

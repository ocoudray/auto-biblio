"""Triage data: what the LLM sees and answers, and the weekly journal of decisions."""

from collections.abc import Mapping
from typing import Literal, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from auto_biblio.domain.errors import LLMOutputInvalidError
from auto_biblio.domain.features import ContextLevel, FeatureVector, ThemeId
from auto_biblio.domain.ids import ItemId, ItemKind

MAX_REASON_WORDS = 30
"""Format constraint of the LLM output: the justification is a single short sentence."""

ItemType = Literal["advance", "tool", "survey", "opinion", "other"]
Level = Literal["low", "medium", "high"]
Slot = Literal["theme", "discovery"]


class TriageInput(BaseModel):
    """An item as the LLM sees it."""

    model_config = ConfigDict(frozen=True)

    ref: str
    """Short reference, unique within a batch (e.g. `i07`)."""
    title: str
    text: str | None
    source: str
    kind: ItemKind
    context_level: ContextLevel


class ThemeScore(BaseModel):
    """Relevance of an item for one theme."""

    model_config = ConfigDict(frozen=True)

    theme: ThemeId
    score: int


class TriageVerdict(BaseModel):
    """The LLM's judgement on one item."""

    model_config = ConfigDict(frozen=True)

    ref: str
    # A list of pairs rather than a mapping: some providers (Gemini) handle object schemas
    # with free-form keys poorly in structured output.
    relevance: tuple[ThemeScore, ...] = Field(
        description="Probable relevance from 0 to 5, only for the themes concerned."
    )
    item_type: ItemType
    novelty: Level
    confidence: Level
    reason: str = Field(description="One sentence, at most 30 words.")

    @field_validator("relevance", mode="before")
    @classmethod
    def _accept_mapping(cls, value: object) -> object:
        # Convenience for callers building verdicts by hand: {theme: score}.
        if isinstance(value, Mapping):
            pairs = cast("Mapping[str, int]", value)
            return [{"theme": theme, "score": score} for theme, score in pairs.items()]
        return value

    def scores(self) -> dict[ThemeId, int]:
        """Return the relevance per theme (the best score if a theme is repeated).

        Returns:
            Score per theme.
        """
        result: dict[ThemeId, int] = {}
        for pair in self.relevance:
            result[pair.theme] = max(pair.score, result.get(pair.theme, 0))
        return result


class TriageBatch(BaseModel):
    """The LLM's answer for a batch of items."""

    model_config = ConfigDict(frozen=True)

    verdicts: tuple[TriageVerdict, ...]


def validate_batch(
    batch: TriageBatch, refs: frozenset[str], themes: frozenset[ThemeId], model_id: str
) -> TriageBatch:
    """Check an LLM answer against the batch it answers.

    Args:
        batch: The parsed answer.
        refs: The refs of the batch.
        themes: The known theme ids.
        model_id: The model that answered, for the error message.

    Returns:
        The batch, unchanged.

    Raises:
        LLMOutputInvalidError: With a message the model can act on when retried.
    """
    problems: list[str] = []
    answered = [verdict.ref for verdict in batch.verdicts]
    if sorted(answered) != sorted(refs):
        missing = sorted(refs - set(answered))
        extra = sorted(set(answered) - refs)
        problems.append(f"refs must be exactly the batch refs (missing {missing}, extra {extra})")
    for verdict in batch.verdicts:
        unknown = sorted({pair.theme for pair in verdict.relevance} - themes)
        if unknown:
            problems.append(f"{verdict.ref}: unknown theme ids {unknown}")
        if any(not 0 <= pair.score <= 5 for pair in verdict.relevance):  # noqa: PLR2004 - the 0-5 scale is part of the output format
            problems.append(f"{verdict.ref}: relevance scores must be between 0 and 5")
        if len(verdict.reason.split()) > MAX_REASON_WORDS:
            problems.append(f"{verdict.ref}: reason longer than {MAX_REASON_WORDS} words")
    if problems:
        raise LLMOutputInvalidError(model_id, "; ".join(problems))
    return batch


class LLMUsage(BaseModel):
    """What one LLM call consumed."""

    model_config = ConfigDict(frozen=True)

    role: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cached: bool
    fallback_from: str | None = None


class ScoredItem(BaseModel):
    """One candidate of a weekly triage, selected or not."""

    model_config = ConfigDict(frozen=True)

    item_id: ItemId
    features: FeatureVector
    prescore: float
    verdict: TriageVerdict | None = None
    """None when the LLM did not triage the item (budget, abandoned batch)."""
    llm_rel: float | None = None
    """LLM relevance on [0, 1], theme weights applied; None when not triaged."""
    final_score: float | None = None
    slot: Slot | None = None
    """None for a candidate that was not selected."""
    theme: ThemeId | None = None
    discovery: bool = False
    """Picked through the discovery slots rather than the profile."""


class ScoringReport(BaseModel):
    """Which scoring produced the final scores, and how well it was evaluated."""

    model_config = ConfigDict(frozen=True)

    version: str
    reliable_labels: int = 0
    auc_without_weak: float | None = None
    auc_with_weak: float | None = None
    coefficients: dict[str, float] = Field(default_factory=dict[str, float])


class TriageRun(BaseModel):
    """The journal of one weekly triage."""

    model_config = ConfigDict(frozen=True)

    week: str
    run_id: str
    generated_at: AwareDatetime
    scoring: ScoringReport
    items: tuple[ScoredItem, ...]
    usage: tuple[LLMUsage, ...] = ()
    degradations: tuple[str, ...] = ()

    def selected(self) -> tuple[ScoredItem, ...]:
        """Return the items shown in the digest, best first.

        Returns:
            The selected items.
        """
        chosen = [item for item in self.items if item.slot is not None]
        return tuple(sorted(chosen, key=lambda s: -(s.final_score or 0.0)))

    def shown_ids(self) -> frozenset[ItemId]:
        """Return the ids of the items shown in the digest.

        Returns:
            The selected ids.
        """
        return frozenset(item.item_id for item in self.items if item.slot is not None)

    def usage_totals(self) -> tuple[float, int]:
        """Sum what the LLM calls of this run consumed.

        Returns:
            Dollars spent and tokens consumed.
        """
        usd = sum(u.cost_usd for u in self.usage)
        tokens = sum(u.input_tokens + u.output_tokens for u in self.usage)
        return usd, tokens

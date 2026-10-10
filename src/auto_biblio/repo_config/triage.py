"""Triage configuration (`config/triage.yaml`): every decision constant of the weekly triage."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    # Unknown keys are rejected so that a typo in `triage.yaml` fails loudly
    # instead of silently keeping the default.
    model_config = ConfigDict(frozen=True, extra="forbid")


class ScoringWeights(_Frozen):
    """Weights of the fixed prescore."""

    relevance: float = Field(default=0.60, ge=0.0)
    popularity: float = Field(default=0.25, ge=0.0)
    multi_source: float = Field(default=0.10, ge=0.0)
    watched: float = Field(default=0.15, ge=0.0)


class DiscoveryConfig(_Frozen):
    """Slots reserved for very popular items outside the profile."""

    slots: int = Field(default=2, ge=0)
    min_popularity: float = Field(default=0.95, ge=0.0, le=1.0)


class RevenantConfig(_Frozen):
    """When an old item comes back into the selection."""

    min_age_days: int = Field(default=30, ge=1)
    min_popularity: float = Field(default=0.90, ge=0.0, le=1.0)
    cooldown_weeks: int = Field(default=8, ge=1)


class RefreshConfig(_Frozen):
    """Daily refresh of the popularity signals of known items."""

    horizon_days: int = Field(default=180, ge=1)
    max_items_per_day: int = Field(default=1000, ge=1)


class LearningConfig(_Frozen):
    """Feedback-driven scoring."""

    min_reliable_labels: int = Field(default=50, ge=2)
    min_per_polarity: int = Field(default=10, ge=1)
    min_auc: float = Field(default=0.65, ge=0.0, le=1.0)
    weak_negative_weight: float = Field(default=0.2, ge=0.0, le=1.0)
    weak_negative_grace_days: int = Field(default=14, ge=0)
    cv_folds: int = Field(default=5, ge=2)

    @model_validator(mode="after")
    def _labels_cover_both_polarities(self) -> Self:
        if self.min_reliable_labels < 2 * self.min_per_polarity:
            msg = "min_reliable_labels must be at least 2 x min_per_polarity"
            raise ValueError(msg)
        return self


FAMILY_COUNT = 4
"""Number of source families (paper, repo, discussion, feed) sharing the family floor."""


class TriageConfig(_Frozen):
    """Every tunable constant of the weekly triage (see the triage spec, section 3.8)."""

    window_days: int = Field(default=7, ge=1)
    reference_days: int = Field(default=28, ge=1)
    min_family_population: int = Field(default=30, ge=1)
    embed_summary_words: int = Field(default=30, ge=0)
    context_max_words: int = Field(default=150, ge=1)
    neutral_popularity: float = Field(default=0.5, ge=0.0, le=1.0)
    weights: ScoringWeights = ScoringWeights()
    relevance_gate: float = Field(default=0.75, ge=0.0, le=1.0)
    candidates: int = Field(default=50, ge=1)
    family_floor: int = Field(default=5, ge=0)
    discovery: DiscoveryConfig = DiscoveryConfig()
    llm_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    llm_gate: int = Field(default=1, ge=0, le=5)
    selected: int = Field(default=18, ge=1)
    per_theme_max: int = Field(default=4, ge=1)
    revenant: RevenantConfig = RevenantConfig()
    refresh: RefreshConfig = RefreshConfig()
    learning: LearningConfig = LearningConfig()
    alert_after_days: int = Field(default=8, ge=1)

    @model_validator(mode="after")
    def _consistent_sizes(self) -> Self:
        if self.selected < self.per_theme_max:
            msg = "selected must be at least per_theme_max"
            raise ValueError(msg)
        if self.candidates < self.family_floor * FAMILY_COUNT:
            msg = f"candidates must be at least family_floor x {FAMILY_COUNT}"
            raise ValueError(msg)
        return self

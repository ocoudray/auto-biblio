"""Analysis configuration (`config/analysis.yaml`): notes, theme pages and full-text limits."""

from pydantic import BaseModel, ConfigDict, Field


class AnalysisConfig(BaseModel):
    """Every tunable constant of the weekly analysis (see the analysis spec, section 3.5)."""

    # Unknown keys are rejected so that a typo fails loudly instead of keeping the default.
    model_config = ConfigDict(frozen=True, extra="forbid")

    deep_count: int = Field(default=4, ge=0)
    """Selected items analysed from their full text each week."""
    max_input_tokens: int = Field(default=30_000, ge=1_000)
    """Size cap of the full text sent for a deep analysis."""
    synthesis_max_input_tokens: int = Field(default=40_000, ge=1_000)
    """Size cap of the notes sent to write a theme page."""
    relevance_threshold: int = Field(default=3, ge=0, le=5)
    """Minimum LLM relevance (0-5) to attach a note to a theme."""
    chars_per_token: float = Field(default=4.0, gt=0)
    """Characters per token, to turn token caps into character caps."""

    @property
    def max_input_chars(self) -> int:
        """Character cap of the full text of a deep analysis."""
        return int(self.max_input_tokens * self.chars_per_token)

    @property
    def synthesis_max_chars(self) -> int:
        """Character cap of the notes sent to write a theme page."""
        return int(self.synthesis_max_input_tokens * self.chars_per_token)

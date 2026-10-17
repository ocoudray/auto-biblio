"""LLM configuration (`config/llm.yaml`): model catalogue, chains per role and weekly budget."""

import math
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from auto_biblio.domain.errors import ConfigError

Role = Literal["triage", "short_note", "deep_analysis", "synthesis", "wiki_link"]
"""What a model is used for."""

LLM_PATH = "config/llm.yaml"

CHARS_PER_TOKEN = 4.0
"""Rough size of a token, used to estimate prompts before sending them."""


class ModelSpec(BaseModel):
    """One model of the catalogue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    """pydantic-ai model identifier, `<provider>:<model>`."""
    input_usd_per_mtok: float = Field(ge=0.0)
    output_usd_per_mtok: float = Field(ge=0.0)
    batch_size: int = Field(ge=1)
    max_output_tokens: int = Field(default=4096, ge=1)
    min_interval_s: float = Field(default=0.0, ge=0.0)
    """Minimum delay between two calls to this model (free tiers cap requests per minute)."""
    max_retries: int = Field(default=2, ge=0)
    """Retries of a call refused by a transient provider error before the chain moves on."""
    tpm: int | None = Field(default=None, ge=1)
    """Tokens per minute the model accepts, if capped; larger calls skip the model."""

    @property
    def is_free(self) -> bool:
        """Whether calls to this model cost nothing (free quota)."""
        return self.input_usd_per_mtok == 0 and self.output_usd_per_mtok == 0

    def call_tokens(self, prompt_chars: int) -> int:
        """Estimate the tokens of a call: the prompt plus the maximum output.

        Args:
            prompt_chars: Length of the whole prompt.

        Returns:
            The estimated tokens.
        """
        return math.ceil(prompt_chars / CHARS_PER_TOKEN) + self.max_output_tokens

    def fits(self, prompt_chars: int) -> bool:
        """Whether a call of this size fits within the model's tokens-per-minute cap.

        Args:
            prompt_chars: Length of the whole prompt.

        Returns:
            True when the model has no cap or the call stays under it.
        """
        return self.tpm is None or self.call_tokens(prompt_chars) <= self.tpm

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        """Price of a call.

        Args:
            input_tokens: Prompt tokens.
            output_tokens: Completion tokens.

        Returns:
            The cost in US dollars.
        """
        return (
            input_tokens * self.input_usd_per_mtok + output_tokens * self.output_usd_per_mtok
        ) / 1_000_000


class Budget(BaseModel):
    """Weekly spending caps."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    usd: float = Field(ge=0.0)
    tokens: int = Field(ge=0)


Chain = Annotated[tuple[str, ...], Field(min_length=1)]


class LLMConfig(BaseModel):
    """The whole `llm.yaml`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    models: dict[str, ModelSpec]
    chains: dict[Role, Chain]
    weekly_budget: Budget

    @model_validator(mode="after")
    def _chains_reference_known_models(self) -> Self:
        for role, names in self.chains.items():
            unknown = [name for name in names if name not in self.models]
            if unknown:
                msg = f"chain {role!r} references unknown model(s): {', '.join(unknown)}"
                raise ValueError(msg)
        return self

    def require(self, *roles: Role) -> None:
        """Check that every given role has a chain.

        A chain is only needed by the step that uses the role, so that an older `llm.yaml`
        keeps serving the steps it covers.

        Args:
            roles: The roles a step needs.

        Raises:
            ConfigError: If a role has no chain.
        """
        missing = [role for role in roles if role not in self.chains]
        if missing:
            msg = f"no chain for role(s) {', '.join(missing)}"
            raise ConfigError(LLM_PATH, "chains", msg)

    def chain(self, role: Role) -> tuple[ModelSpec, ...]:
        """Return the models tried, in order, for a role.

        Args:
            role: The role.

        Returns:
            The model specs of the chain.

        Raises:
            ConfigError: If the role has no chain.
        """
        self.require(role)
        return tuple(self.models[name] for name in self.chains[role])

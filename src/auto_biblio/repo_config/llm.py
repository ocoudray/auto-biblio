"""LLM configuration (`config/llm.yaml`): model catalogue, chains per role and weekly budget."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Role = Literal["triage"]
"""What a model is used for; later sub-projects add their own roles."""

ROLES: tuple[Role, ...] = ("triage",)


class ModelSpec(BaseModel):
    """One model of the catalogue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    """pydantic-ai model identifier, `<provider>:<model>`."""
    input_usd_per_mtok: float = Field(ge=0.0)
    output_usd_per_mtok: float = Field(ge=0.0)
    batch_size: int = Field(ge=1)
    max_output_tokens: int = Field(default=4096, ge=1)

    @property
    def is_free(self) -> bool:
        """Whether calls to this model cost nothing (free quota)."""
        return self.input_usd_per_mtok == 0 and self.output_usd_per_mtok == 0

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
        for role in ROLES:
            if role not in self.chains:
                msg = f"missing chain for role {role!r}"
                raise ValueError(msg)
        for role, names in self.chains.items():
            unknown = [name for name in names if name not in self.models]
            if unknown:
                msg = f"chain {role!r} references unknown model(s): {', '.join(unknown)}"
                raise ValueError(msg)
        return self

    def chain(self, role: Role) -> tuple[ModelSpec, ...]:
        """Return the models tried, in order, for a role.

        Args:
            role: The role.

        Returns:
            The model specs of the chain.
        """
        return tuple(self.models[name] for name in self.chains[role])

"""A scripted `ModelRunner` for the LLM layer tests."""

from pydantic import BaseModel

from auto_biblio.domain.triage import LLMUsage
from auto_biblio.llm import LLMResult, LLMTask
from auto_biblio.repo_config.llm import LLMConfig, ModelSpec

CONFIG = LLMConfig.model_validate(
    {
        "models": {
            "free": {
                "id": "t:free",
                "input_usd_per_mtok": 0,
                "output_usd_per_mtok": 0,
                "batch_size": 5,
            },
            "paid": {
                "id": "t:paid",
                "input_usd_per_mtok": 1,
                "output_usd_per_mtok": 5,
                "batch_size": 5,
            },
        },
        "chains": {"triage": ["free", "paid"]},
        "weekly_budget": {"usd": 1, "tokens": 1_000_000},
    }
)


class Answer(BaseModel):
    value: int


def make_task(user: str = "u") -> LLMTask[Answer]:
    return LLMTask(
        role="triage", prompt_version="v1", system_prompt="s", user_prompt=user, output_type=Answer
    )


class ScriptedRunner:
    """Pops one scripted outcome (an exception or a value) per call, per model."""

    def __init__(self, script: dict[str, list[Exception | int]]) -> None:
        self.script = script
        self.calls: list[tuple[str, str]] = []

    def run[T: BaseModel](self, task: LLMTask[T], spec: ModelSpec) -> LLMResult[T]:
        self.calls.append((spec.id, task.user_prompt))
        outcome = self.script[spec.id].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        usage = LLMUsage(
            role=task.role,
            model_id=spec.id,
            input_tokens=100,
            output_tokens=10,
            cost_usd=spec.cost_usd(100, 10),
            cached=False,
        )
        return LLMResult(output=task.output_type.model_validate({"value": outcome}), usage=usage)


def ignore_fallback(_role: str, _model_id: str, _reason: str) -> None:
    """Fallback hook that does nothing."""

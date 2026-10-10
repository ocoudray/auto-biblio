"""Provider-agnostic structured LLM calls: a task in, a validated Pydantic object out."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel

from auto_biblio.domain.triage import LLMUsage
from auto_biblio.repo_config.llm import ModelSpec, Role

__all__ = ["LLMResult", "LLMTask", "LLMUsage", "ModelRunner", "StructuredLLM"]


def _unchanged[T](output: T, _model_id: str) -> T:
    return output


@dataclass(frozen=True)
class LLMTask[T: BaseModel]:
    """One structured call: prompts, expected output type and extra validation.

    A dataclass rather than a Pydantic model: it carries a type and a function, not data.
    """

    role: Role
    prompt_version: str
    system_prompt: str
    user_prompt: str
    output_type: type[T]
    validate: Callable[[T, str], T] = field(default=_unchanged)
    """Checks the parsed output against the task (given the model id); raises
    `LLMOutputInvalidError` with a message the model can act on."""

    def with_feedback(self, error: str) -> "LLMTask[T]":
        """Return the same task, with a validation error appended for a retry.

        Args:
            error: What was wrong with the previous answer.

        Returns:
            The task to retry.
        """
        note = f"\n\nYour previous answer was rejected: {error}\nAnswer again, fixing this."
        return LLMTask(
            role=self.role,
            prompt_version=self.prompt_version,
            system_prompt=self.system_prompt,
            user_prompt=self.user_prompt + note,
            output_type=self.output_type,
            validate=self.validate,
        )


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    """A validated output and what producing it cost."""

    output: T
    usage: LLMUsage


class StructuredLLM(Protocol):
    """Runs a task with whatever model the implementation chooses."""

    def run[T: BaseModel](self, task: LLMTask[T]) -> LLMResult[T]:
        """Run a task.

        Args:
            task: The task.

        Returns:
            The validated output and its usage.
        """
        ...


class ModelRunner(Protocol):
    """Runs a task with one given model."""

    def run[T: BaseModel](self, task: LLMTask[T], spec: ModelSpec) -> LLMResult[T]:
        """Run a task with a model.

        Args:
            task: The task.
            spec: The model.

        Returns:
            The validated output and its usage.
        """
        ...

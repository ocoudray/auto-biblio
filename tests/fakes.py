"""Fakes of the true external boundaries, shared across test modules."""

import hashlib
import json
import re
from collections.abc import Sequence
from typing import cast

import numpy as np
from pydantic import BaseModel

from auto_biblio.domain.triage import LLMUsage, TriageBatch
from auto_biblio.embeddings import Vector
from auto_biblio.llm import LLMResult, LLMTask
from auto_biblio.repo_config.llm import ModelSpec


class FakeEmbedder:
    """Deterministic embedder: the vector of a text derives from its hash."""

    def __init__(self, dim: int = 16) -> None:
        self.dim = dim
        self.calls: list[list[str]] = []

    @property
    def model_id(self) -> str:
        return "fake/hash"

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        self.calls.append(list(texts))
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> Vector:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
        raw = np.random.default_rng(seed).normal(size=self.dim)
        return tuple(float(x) for x in raw / np.linalg.norm(raw))


def verdicts_for(task: LLMTask[TriageBatch]) -> TriageBatch:
    """Answer a triage task like a sensible model: theme words in the title score 4.

    "agent" maps to the theme whose id starts with `agentic`, "retrieval" to the one
    starting with `rag`, among the ids listed in the system prompt.
    """
    payload = task.user_prompt.split("\n", 1)[1].split("\n\nYour previous answer", 1)[0]
    items: list[dict[str, str]] = json.loads(payload)
    ids = re.findall(r"- id: (\S+)", task.system_prompt)
    words = {"agent": "agentic", "retrieval": "rag"}
    verdicts: list[dict[str, object]] = []
    for item in items:
        title = item["title"].lower()
        relevance = [
            {"theme": theme, "score": 0 if "hype" in title else 4}
            for word, prefix in words.items()
            for theme in ids
            if word in title and theme.startswith(prefix)
        ]
        verdicts.append(
            {
                "ref": item["ref"],
                "relevance": relevance,
                "item_type": "tool",
                "novelty": "high",
                "confidence": "high",
                "reason": f"About {title}.",
            }
        )
    return TriageBatch.model_validate({"verdicts": verdicts})


class FakeRunner:
    """`ModelRunner` answering triage tasks with `verdicts_for`; counts its calls."""

    def __init__(self) -> None:
        self.calls = 0

    def run[T: BaseModel](self, task: LLMTask[T], spec: ModelSpec) -> LLMResult[T]:
        self.calls += 1
        triage = cast("LLMTask[TriageBatch]", task)  # only triage tasks exist so far
        output = task.output_type.model_validate(verdicts_for(triage).model_dump())
        usage = LLMUsage(
            role=task.role,
            model_id=spec.id,
            input_tokens=500,
            output_tokens=100,
            cost_usd=0.0,
            cached=False,
        )
        return LLMResult(output=task.validate(output, spec.id), usage=usage)


def ignore_fallback(_role: str, _model_id: str, _reason: str) -> None:
    """Fallback hook that does nothing."""

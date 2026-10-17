"""Fakes of the true external boundaries, shared across test modules."""

import hashlib
import json
import re
from collections.abc import Sequence
from typing import cast

import numpy as np
from pydantic import BaseModel

from auto_biblio.domain.errors import ProviderUnavailableError
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


def answer_for(task: LLMTask[BaseModel]) -> dict[str, object]:
    """Answer any task of the pipeline like a sensible model."""
    name = task.output_type.__name__
    if name == "LinkBatch":
        notes = cast("list[dict[str, str]]", json.loads(task.user_prompt.removeprefix("Notes:\n")))
        linked = ["llm/attention"] if '"llm/attention"' in task.system_prompt else []
        return {
            "links": [{"ref": n["ref"], "notions": linked, "missing": ["KV cache"]} for n in notes]
        }
    if name == "TriageBatch":
        return verdicts_for(cast("LLMTask[TriageBatch]", task)).model_dump()
    short: dict[str, object] = {
        "summary": "Résumé.",
        "contribution": "Apport.",
        "relevance": "Utile.",
    }
    if name == "ShortNote":
        return short
    if name == "DeepAnalysis":
        return short | {
            "problem": "Problème.",
            "method": ["Étape"],
            "results": ["+10 %"],
            "limitations": [],
            "positioning": "Position.",
            "takeaways": ["À essayer"],
            "further_reading": [],
            "verdict": "À lire.",
            "confidence": "high",
        }
    payload: dict[str, object] = json.loads(task.user_prompt)
    previous = cast("dict[str, list[object]] | None", payload["previous_page"])
    notes = cast("list[dict[str, str]]", payload["notes"])
    kept = list(previous["further_reading"]) if previous else []
    return {
        "overview": "Vue.",
        "key_concepts": ["Concept"],
        "dominant_approaches": [],
        "reference_tools": [
            {"name": n["title"], "url": n["url"], "note_id": n["id"]} for n in notes[:2]
        ],
        "open_questions": [],
        "further_reading": sorted({*map(str, kept), "https://example.org/survey"}),
    }


class PipelineRunner:
    """`ModelRunner` answering every role with `answer_for`; counts calls per role."""

    def __init__(self, failing: dict[str, set[str]] | None = None) -> None:
        self.calls: list[str] = []
        self.failing = failing or {}
        """Roles each model id fails on (provider unavailable)."""

    def run[T: BaseModel](self, task: LLMTask[T], spec: ModelSpec) -> LLMResult[T]:
        self.calls.append(task.role)
        if task.role in self.failing.get(spec.id, set()):
            message = "down"
            raise ProviderUnavailableError(spec.id, message)
        output = task.output_type.model_validate(answer_for(cast("LLMTask[BaseModel]", task)))
        usage = LLMUsage(
            role=task.role,
            model_id=spec.id,
            input_tokens=1000,
            output_tokens=200,
            cost_usd=0.0,
            cached=False,
        )
        return LLMResult(output=task.validate(output, spec.id), usage=usage)

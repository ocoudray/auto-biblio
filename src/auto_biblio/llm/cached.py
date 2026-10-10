"""Response cache in front of the whole chain: a replayed week costs nothing."""

import hashlib
import json
from collections.abc import Sequence

from pydantic import BaseModel

from auto_biblio.domain.triage import LLMUsage
from auto_biblio.llm import LLMResult, LLMTask, StructuredLLM
from auto_biblio.repo_config.llm import LLMConfig
from auto_biblio.store.llm_cache import LLMCacheStore


class CachedLLM:
    """`StructuredLLM` that answers from the cache when any model of the chain already did."""

    def __init__(self, inner: StructuredLLM, store: LLMCacheStore, config: LLMConfig) -> None:
        """Build the cache.

        Args:
            inner: Called on cache misses.
            store: Where outputs are kept.
            config: Gives the models of each role's chain.
        """
        self._inner = inner
        self._store = store
        self._config = config

    def run[T: BaseModel](self, task: LLMTask[T]) -> LLMResult[T]:
        """Run a task, from the cache if possible.

        Args:
            task: The task.

        Returns:
            The output; a cached one comes with a free, `cached=True` usage.
        """
        model_ids = [spec.id for spec in self._config.chain(task.role)]
        hit = self._lookup(task, model_ids)
        if hit is not None:
            return hit
        result = self._inner.run(task)
        self._store.put(
            task.prompt_version,
            cache_key(task, result.usage.model_id),
            result.output.model_dump_json(),
        )
        return result

    def _lookup[T: BaseModel](
        self, task: LLMTask[T], model_ids: Sequence[str]
    ) -> LLMResult[T] | None:
        for model_id in model_ids:
            raw = self._store.get(task.prompt_version, cache_key(task, model_id))
            if raw is None:
                continue
            usage = LLMUsage(
                role=task.role,
                model_id=model_id,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                cached=True,
            )
            return LLMResult(output=task.output_type.model_validate_json(raw), usage=usage)
        return None


def cache_key[T: BaseModel](task: LLMTask[T], model_id: str) -> str:
    """Hash what determines an answer: prompt version, model and prompts.

    Args:
        task: The task.
        model_id: The model.

    Returns:
        A hex SHA-256.
    """
    material = json.dumps(
        [task.prompt_version, model_id, task.system_prompt, task.user_prompt], ensure_ascii=False
    )
    return hashlib.sha256(material.encode()).hexdigest()

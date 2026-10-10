from pathlib import Path

from scripted import CONFIG, Answer, ScriptedRunner, ignore_fallback, make_task

from auto_biblio.domain.errors import ProviderQuotaError
from auto_biblio.llm.cached import CachedLLM, cache_key
from auto_biblio.llm.chain import ModelChain
from auto_biblio.store.llm_cache import LLMCacheStore


def cached(tmp_path: Path, runner: ScriptedRunner) -> CachedLLM:
    return CachedLLM(ModelChain(runner, CONFIG, ignore_fallback), LLMCacheStore(tmp_path), CONFIG)


def test_cache_hit_is_free(tmp_path: Path) -> None:
    runner = ScriptedRunner({"t:free": [7]})
    llm = cached(tmp_path, runner)
    first = llm.run(make_task())
    second = llm.run(make_task())
    assert first.output == second.output == Answer(value=7)
    assert len(runner.calls) == 1
    assert second.usage.cached
    assert second.usage.cost_usd == 0
    assert second.usage.input_tokens == 0


def test_cache_hit_on_fallback_model(tmp_path: Path) -> None:
    runner = ScriptedRunner({"t:free": [ProviderQuotaError("t:free", "429")], "t:paid": [8]})
    llm = cached(tmp_path, runner)
    llm.run(make_task())
    again = llm.run(make_task())
    assert again.usage.model_id == "t:paid"
    assert again.usage.cached
    assert len(runner.calls) == 2


def test_cache_key_depends_on_prompt_and_model() -> None:
    assert cache_key(make_task("a"), "m") != cache_key(make_task("b"), "m")
    assert cache_key(make_task("a"), "m") != cache_key(make_task("a"), "n")
    assert cache_key(make_task("a"), "m") == cache_key(make_task("a"), "m")

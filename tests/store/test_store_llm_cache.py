from pathlib import Path

from auto_biblio.store.llm_cache import LLMCacheStore


def test_llm_cache_miss_then_hit(tmp_path: Path) -> None:
    store = LLMCacheStore(tmp_path)
    assert store.get("triage_v1", "abc") is None
    store.put("triage_v1", "abc", '{"verdicts": []}')
    assert store.get("triage_v1", "abc") == '{"verdicts": []}\n'
    assert (tmp_path / "llm_cache" / "triage_v1" / "abc.json").exists()

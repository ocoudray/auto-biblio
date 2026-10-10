from pathlib import Path

import numpy as np
import pytest
from fakes import FakeEmbedder

from auto_biblio.embeddings.cache import CachedEmbedder


def test_cache_calls_inner_only_for_misses(tmp_path: Path) -> None:
    inner = FakeEmbedder()
    cache = CachedEmbedder(inner, tmp_path)
    first = cache.embed(["a", "b", "a"])
    second = cache.embed(["b", "c"])
    assert inner.calls == [["a", "b"], ["c"]]
    assert first[0] == first[2]
    assert second[0] == first[1]
    assert cache.model_id == "fake/hash"


def test_cache_persists_across_instances(tmp_path: Path) -> None:
    cache = CachedEmbedder(FakeEmbedder(), tmp_path)
    vectors = cache.embed(["a", "b"])
    cache.flush()
    cache.flush()  # nothing new: no extra shard
    assert len(list((tmp_path / "fake_hash").glob("*.npz"))) == 1
    inner = FakeEmbedder()
    reloaded = CachedEmbedder(inner, tmp_path).embed(["a", "b"])
    assert inner.calls == []
    assert np.allclose(reloaded, vectors, atol=1e-6)  # float32 storage


def test_corrupt_shard_ignored(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    shard_dir = tmp_path / "fake_hash"
    shard_dir.mkdir()
    (shard_dir / "bad.npz").write_bytes(b"not a zip")
    inner = FakeEmbedder()
    CachedEmbedder(inner, tmp_path).embed(["a"])
    assert inner.calls == [["a"]]
    assert "unreadable embedding shard" in caplog.text

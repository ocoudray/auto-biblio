from collections.abc import Iterable

import numpy as np
import pytest
from numpy.typing import ArrayLike

from auto_biblio.domain.errors import EmbeddingError
from auto_biblio.embeddings.fastembed import FastEmbedder


class Engine:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def embed(self, documents: list[str]) -> Iterable[ArrayLike]:
        if self.fail:
            msg = "onnx exploded"
            raise RuntimeError(msg)
        return [np.array([3.0, 4.0]) if d else np.zeros(2) for d in documents]


def test_fastembed_normalizes() -> None:
    embedder = FastEmbedder(Engine(), "m")
    assert embedder.model_id == "m"
    assert embedder.embed(["x", ""]) == [(0.6, 0.8), (0.0, 0.0)]
    assert embedder.embed([]) == []


def test_fastembed_wraps_engine_error() -> None:
    with pytest.raises(EmbeddingError, match="onnx exploded"):
        FastEmbedder(Engine(fail=True), "m").embed(["x"])

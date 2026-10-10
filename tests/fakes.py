"""Fakes of the true external boundaries, shared across test modules."""

import hashlib
from collections.abc import Sequence

import numpy as np

from auto_biblio.embeddings import Vector


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

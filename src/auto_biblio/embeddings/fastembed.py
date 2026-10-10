"""fastembed implementation of `Embedder` (ONNX runtime, CPU, no torch)."""

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Protocol, Self

import numpy as np
from numpy.typing import ArrayLike, NDArray

from auto_biblio.domain.errors import EmbeddingError
from auto_biblio.embeddings import Vector

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class EmbeddingEngine(Protocol):
    """The part of `fastembed.TextEmbedding` we use."""

    def embed(self, documents: list[str]) -> Iterable[ArrayLike]:
        """Embed documents.

        Args:
            documents: The texts.

        Returns:
            One raw vector per text.
        """
        ...


class FastEmbedder:
    """Embeds with a fastembed engine and L2-normalizes the vectors."""

    def __init__(self, engine: EmbeddingEngine, model_id: str) -> None:
        """Wrap an engine.

        Args:
            engine: A loaded fastembed model (or a fake in tests).
            model_id: Name of the model.
        """
        self._engine = engine
        self._model_id = model_id

    @classmethod
    def load(
        cls, model_id: str = DEFAULT_MODEL, cache_dir: Path | None = None
    ) -> Self:  # pragma: no cover - downloads the model; exercised by the weekly workflow
        """Load a fastembed model, downloading it on first use.

        Args:
            model_id: fastembed model name.
            cache_dir: Where the model files are kept.

        Returns:
            The embedder.

        Raises:
            EmbeddingError: If the model cannot be loaded.
        """
        from fastembed import TextEmbedding  # noqa: PLC0415 - heavy import, only when needed

        try:
            engine = TextEmbedding(
                model_name=model_id, cache_dir=str(cache_dir) if cache_dir else None
            )
        except (OSError, ValueError, RuntimeError) as exc:
            msg = f"cannot load embedding model {model_id!r}: {exc}"
            raise EmbeddingError(msg) from exc
        return cls(engine, model_id)

    @property
    def model_id(self) -> str:
        """Name of the model."""
        return self._model_id

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        """Embed texts.

        Args:
            texts: The texts.

        Returns:
            One L2-normalized vector per text.

        Raises:
            EmbeddingError: If the engine fails.
        """
        if not texts:
            return []
        try:
            raw = [np.asarray(v, dtype=np.float64) for v in self._engine.embed(list(texts))]
        except (OSError, ValueError, RuntimeError) as exc:
            msg = f"embedding failed with {self._model_id!r}: {exc}"
            raise EmbeddingError(msg) from exc
        return [_normalized(vector) for vector in raw]


def _normalized(vector: NDArray[np.float64]) -> Vector:
    norm = float(np.linalg.norm(vector))
    scaled = vector / norm if norm > 0 else vector
    return tuple(float(x) for x in scaled)

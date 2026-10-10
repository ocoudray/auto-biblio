"""On-disk cache of embeddings: vectors are derived data, recomputed when the cache is lost."""

import hashlib
import logging
import re
import zipfile
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from auto_biblio.embeddings import Embedder, Vector

logger = logging.getLogger(__name__)


class CachedEmbedder:
    """Wraps an `Embedder`; only texts never seen before are embedded.

    Vectors are kept in `.npz` shards under `<cache_dir>/<model slug>/`, keyed by the
    SHA-256 of the text. Each `flush` writes a new shard with the vectors computed since.
    """

    def __init__(self, inner: Embedder, cache_dir: Path) -> None:
        """Load the existing shards of the model.

        Args:
            inner: The embedder called on cache misses.
            cache_dir: Root of the cache.
        """
        self._inner = inner
        self._dir = cache_dir / re.sub(r"[^\w.-]+", "_", inner.model_id)
        self._vectors: dict[str, Vector] = {}
        self._new: dict[str, Vector] = {}
        for shard in sorted(self._dir.glob("*.npz")):
            self._load(shard)

    @property
    def model_id(self) -> str:
        """Name of the wrapped model."""
        return self._inner.model_id

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        """Embed texts, calling the wrapped embedder only for unknown ones.

        Args:
            texts: The texts.

        Returns:
            One vector per text.
        """
        keys = [_key(text) for text in texts]
        missing = list(
            {k: t for k, t in zip(keys, texts, strict=True) if k not in self._vectors}.items()
        )
        if missing:
            vectors = self._inner.embed([text for _, text in missing])
            for (key, _), vector in zip(missing, vectors, strict=True):
                self._vectors[key] = vector
                self._new[key] = vector
        return [self._vectors[key] for key in keys]

    def flush(self) -> None:
        """Write the vectors computed since the last flush to a new shard."""
        if not self._new:
            return
        self._dir.mkdir(parents=True, exist_ok=True)
        keys = sorted(self._new)
        name = hashlib.sha256("".join(keys).encode()).hexdigest()[:16]
        np.savez_compressed(
            self._dir / f"{name}.npz",
            keys=np.asarray(keys),
            vectors=np.asarray([self._new[k] for k in keys], dtype=np.float32),
        )
        self._new.clear()

    def _load(self, shard: Path) -> None:
        try:
            with np.load(shard) as data:
                keys = [str(k) for k in data["keys"]]
                vectors = data["vectors"].astype(np.float64)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            logger.warning("ignoring unreadable embedding shard %s: %s", shard, exc)
            return
        for key, vector in zip(keys, vectors, strict=True):
            self._vectors[key] = tuple(float(x) for x in vector)


def _key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

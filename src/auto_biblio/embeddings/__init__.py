"""Local text embeddings: the `Embedder` port and its implementations."""

from collections.abc import Sequence
from typing import Protocol

type Vector = tuple[float, ...]


class Embedder(Protocol):
    """Turns texts into L2-normalized vectors."""

    @property
    def model_id(self) -> str:
        """Identifies the model, so that vectors of different models never mix."""
        ...

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        """Embed texts.

        Args:
            texts: The texts.

        Returns:
            One normalized vector per text, in order.
        """
        ...

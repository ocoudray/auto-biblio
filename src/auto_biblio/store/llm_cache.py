"""LLM response cache, committed with the data so that replaying a week costs nothing."""

from pathlib import Path

from auto_biblio.store._files import atomic_write_text


class LLMCacheStore:
    """Validated LLM outputs in `state/llm_cache/<prompt version>/<key>.json`."""

    def __init__(self, state_dir: Path) -> None:
        """Build the store.

        Args:
            state_dir: The data repository's `state/` directory.
        """
        self._dir = state_dir / "llm_cache"

    def get(self, prompt_version: str, key: str) -> str | None:
        """Read a cached output.

        Args:
            prompt_version: Version of the prompt.
            key: Hash of the call.

        Returns:
            The cached JSON, if any.
        """
        path = self._dir / prompt_version / f"{key}.json"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def put(self, prompt_version: str, key: str, payload_json: str) -> None:
        """Cache an output.

        Args:
            prompt_version: Version of the prompt.
            key: Hash of the call.
            payload_json: The validated output, as JSON.
        """
        atomic_write_text(self._dir / prompt_version / f"{key}.json", payload_json + "\n")

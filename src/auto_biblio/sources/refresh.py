"""Clients that re-read the popularity of known items: GitHub stars and HF upvotes."""

import re
from collections.abc import Sequence

import httpx
from pydantic import BaseModel, SecretStr, TypeAdapter

from auto_biblio.domain.errors import SourcePayloadError, SourceUnavailableError
from auto_biblio.sources._http import Throttle, get, parse_json

GRAPHQL_URL = "https://api.github.com/graphql"
HF_PAPER_URL = "https://huggingface.co/api/papers/{arxiv_id}"
GRAPHQL_BATCH = 100
_NAME = re.compile(r"^[\w.-]+$")
HTTP_NOT_FOUND = 404


class _Stars(BaseModel):
    stargazerCount: int  # noqa: N815 - mirrors the API field name


class _GraphQLAnswer(BaseModel):
    data: dict[str, _Stars | None] | None = None


class _HfPaper(BaseModel):
    upvotes: int = 0


_ANSWER = TypeAdapter(_GraphQLAnswer)
_PAPER = TypeAdapter(_HfPaper)


class GithubStarsClient:
    """Reads the star count of many repositories with batched GraphQL queries."""

    source = "refresh:gh_stars"

    def __init__(self, client: httpx.Client, token: SecretStr) -> None:
        """Build the client.

        Args:
            client: Injected HTTP client.
            token: GitHub token (GraphQL requires authentication).
        """
        self._client = client
        self._token = token

    def stars(self, repos: Sequence[str]) -> dict[str, int]:
        """Read the stars of repositories.

        Args:
            repos: `owner/repo` names.

        Returns:
            Stars per repository; repositories not found are absent.

        Raises:
            SourceUnavailableError: On network errors and non-2xx statuses.
            SourcePayloadError: On an unexpected answer.
        """
        valid = [r for r in repos if all(_NAME.match(part) for part in r.split("/", 1))]
        result: dict[str, int] = {}
        for start in range(0, len(valid), GRAPHQL_BATCH):
            result.update(self._batch(valid[start : start + GRAPHQL_BATCH]))
        return result

    def _batch(self, repos: Sequence[str]) -> dict[str, int]:
        fields = " ".join(
            f'r{i}: repository(owner: "{owner}", name: "{name}") {{ stargazerCount }}'
            for i, (owner, name) in enumerate(r.split("/", 1) for r in repos)
        )
        headers = {"Authorization": f"Bearer {self._token.get_secret_value()}"}
        try:
            response = self._client.post(
                GRAPHQL_URL, json={"query": f"query {{ {fields} }}"}, headers=headers
            )
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(self.source, f"GraphQL request failed: {exc}") from exc
        if not response.is_success:
            message = f"HTTP {response.status_code} from GraphQL"
            raise SourceUnavailableError(self.source, message, response.status_code)
        answer = parse_json(response, _ANSWER, source=self.source)
        if answer.data is None:
            raise SourcePayloadError(self.source, "GraphQL answer without data", response.text)
        return {
            repo: stars.stargazerCount
            for i, repo in enumerate(repos)
            if (stars := answer.data.get(f"r{i}")) is not None
        }


class HfUpvotesClient:
    """Reads the upvotes of a paper on Hugging Face."""

    source = "refresh:hf_upvotes"

    def __init__(self, client: httpx.Client, throttle: Throttle) -> None:
        """Build the client.

        Args:
            client: Injected HTTP client.
            throttle: Request pacing.
        """
        self._client = client
        self._throttle = throttle

    def upvotes(self, arxiv_id: str) -> int | None:
        """Read the upvotes of a paper.

        Args:
            arxiv_id: The arXiv identifier, without prefix.

        Returns:
            The upvotes, or None if Hugging Face does not know the paper.

        Raises:
            SourceUnavailableError: On network errors and non-2xx statuses other than 404.
            SourcePayloadError: On an unexpected answer.
        """
        self._throttle.wait()
        url = HF_PAPER_URL.format(arxiv_id=arxiv_id)
        try:
            response = get(self._client, url, source=self.source, throttle=self._throttle)
        except SourceUnavailableError as exc:
            if exc.status_code == HTTP_NOT_FOUND:
                return None
            raise
        return parse_json(response, _PAPER, source=self.source).upvotes

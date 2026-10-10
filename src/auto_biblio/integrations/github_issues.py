"""GitHub issues of the data repository: the channel of explicit feedback."""

from collections.abc import Mapping

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, SecretStr, TypeAdapter

from auto_biblio.domain.errors import SourceUnavailableError
from auto_biblio.sources._http import get, parse_json

API_URL = "https://api.github.com"
FEEDBACK_LABEL = "feedback"
INVALID_LABEL = "feedback-invalid"
_SOURCE = "github-issues"


class _Label(BaseModel):
    name: str


class Issue(BaseModel):
    """An open issue, as far as feedback is concerned."""

    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    body: str | None = None
    created_at: AwareDatetime
    labels: tuple[_Label, ...] = ()
    pull_request: dict[str, object] | None = None
    """Present when the "issue" is a pull request (the API mixes both)."""

    @property
    def label_names(self) -> frozenset[str]:
        """Names of the issue's labels."""
        return frozenset(label.name for label in self.labels)


_ISSUES = TypeAdapter(list[Issue])


class GithubIssues:
    """Reads and updates the feedback issues of one repository."""

    def __init__(self, client: httpx.Client, repo: str, token: SecretStr) -> None:
        """Build the client.

        Args:
            client: Injected HTTP client.
            repo: `owner/repo` of the data repository.
            token: Token allowed to write issues.
        """
        self._client = client
        self._repo = repo
        self._headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token.get_secret_value()}",
        }

    def open_feedback(self) -> tuple[Issue, ...]:
        """List the open issues labelled `feedback`, following pagination.

        Returns:
            The issues (pull requests excluded), oldest first.

        Raises:
            SourceUnavailableError: On network errors and non-2xx statuses.
            SourcePayloadError: On an unexpected answer.
        """
        url: str | None = f"{API_URL}/repos/{self._repo}/issues"
        params: Mapping[str, str | int] | None = {
            "state": "open",
            "labels": FEEDBACK_LABEL,
            "per_page": 100,
            "direction": "asc",
        }
        issues: list[Issue] = []
        while url is not None:
            response = get(self._client, url, source=_SOURCE, params=params, headers=self._headers)
            issues.extend(parse_json(response, _ISSUES, source=_SOURCE))
            url = response.links.get("next", {}).get("url")
            params = None  # the next link already carries them
        return tuple(i for i in issues if i.pull_request is None)

    def comment(self, number: int, body: str) -> None:
        """Comment on an issue.

        Args:
            number: The issue.
            body: Markdown text.
        """
        self._send("POST", f"/issues/{number}/comments", {"body": body})

    def add_label(self, number: int, label: str) -> None:
        """Add a label to an issue.

        Args:
            number: The issue.
            label: The label name.
        """
        self._send("POST", f"/issues/{number}/labels", {"labels": [label]})

    def close(self, number: int) -> None:
        """Close an issue as completed.

        Args:
            number: The issue.
        """
        self._send("PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "completed"})

    def _send(self, method: str, path: str, payload: Mapping[str, object]) -> None:
        url = f"{API_URL}/repos/{self._repo}{path}"
        try:
            response = self._client.request(method, url, json=payload, headers=self._headers)
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(_SOURCE, f"{method} {url} failed: {exc}") from exc
        if not response.is_success:
            message = f"HTTP {response.status_code} from {method} {url}"
            raise SourceUnavailableError(_SOURCE, message, response.status_code)

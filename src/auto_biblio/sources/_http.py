"""HTTP helpers shared by connectors: polite throttling and error mapping."""

import time
from collections.abc import Callable, Mapping

import httpx
from pydantic import TypeAdapter, ValidationError

from auto_biblio.domain.errors import SourcePayloadError, SourceUnavailableError


class Throttle:
    """Enforce a minimum delay between consecutive requests of one source."""

    def __init__(
        self,
        min_interval_s: float,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Build the throttle.

        Args:
            min_interval_s: Minimum delay between two `wait` returns.
            monotonic: Clock (injected for tests).
            sleep: Sleep function (injected for tests).
        """
        self._interval = min_interval_s
        self._monotonic = monotonic
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        """Block until the next request is allowed; the first call never blocks."""
        if self._last is not None:
            remaining = self._interval - (self._monotonic() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._monotonic()


def get(
    client: httpx.Client,
    url: str,
    *,
    source: str,
    params: Mapping[str, str | int] | None = None,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    """GET a URL, turning every transport failure and non-2xx status into one error type.

    Args:
        client: Injected HTTP client.
        url: Target URL.
        source: Source name, for error messages.
        params: Query parameters.
        headers: Extra request headers.

    Returns:
        The successful response.

    Raises:
        SourceUnavailableError: On network errors, timeouts and non-2xx statuses.
    """
    try:
        response = client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise SourceUnavailableError(source, f"request to {url} failed: {exc}") from exc
    if not response.is_success:
        message = f"HTTP {response.status_code} from {url}"
        raise SourceUnavailableError(source, message, response.status_code)
    return response


def parse_json[T](response: httpx.Response, adapter: TypeAdapter[T], *, source: str) -> T:
    """Validate a JSON response body against a model.

    Args:
        response: Successful response.
        adapter: Expected shape of the body.
        source: Source name, for error messages.

    Returns:
        The validated body.

    Raises:
        SourcePayloadError: If the body is not JSON or does not match the model.
    """
    try:
        return adapter.validate_json(response.content)
    except ValidationError as exc:
        message = f"unexpected payload: {exc.errors()[0]['msg']}"
        raise SourcePayloadError(source, message, response.text) from exc

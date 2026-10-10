"""HTTP helpers shared by connectors: polite throttling and error mapping."""

import logging
import time
from collections.abc import Callable, Mapping

import httpx
from pydantic import TypeAdapter, ValidationError

from auto_biblio.domain.errors import SourcePayloadError, SourceUnavailableError

logger = logging.getLogger(__name__)


RETRYABLE_STATUSES = frozenset({429, 503})
RETRY_AFTER_MAX_S = 120.0


class Throttle:
    """Pace the requests of one source and decide how long to back off when it pushes back."""

    def __init__(
        self,
        min_interval_s: float,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        *,
        max_retries: int = 3,
        retry_base_s: float = 10.0,
    ) -> None:
        """Build the throttle.

        Args:
            min_interval_s: Minimum delay between two `wait` returns.
            monotonic: Clock (injected for tests).
            sleep: Sleep function (injected for tests).
            max_retries: Retries allowed per request on a rate-limit or unavailable answer.
            retry_base_s: First backoff delay when the server gives no `Retry-After`;
                doubled at each retry.
        """
        self._interval = min_interval_s
        self._monotonic = monotonic
        self._sleep = sleep
        self._max_retries = max_retries
        self._retry_base = retry_base_s
        self._last: float | None = None

    def retry_delay(self, attempt: int, retry_after: str | None) -> float | None:
        """Delay before retrying a pushed-back request, or None to give up.

        Args:
            attempt: Number of retries already made for this request.
            retry_after: The server's `Retry-After` header (seconds), if any.

        Returns:
            Seconds to wait (`Retry-After` capped at 120 s, else exponential backoff),
            or None once `max_retries` is reached.
        """
        if attempt >= self._max_retries:
            return None
        if retry_after is not None and retry_after.strip().isdigit():
            return min(float(retry_after), RETRY_AFTER_MAX_S)
        return self._retry_base * 2**attempt

    def pause(self, seconds: float) -> None:
        """Sleep, then count the pause as the last request time."""
        self._sleep(seconds)
        self._last = self._monotonic()

    def wait(self) -> None:
        """Block until the next request is allowed; the first call never blocks."""
        if self._last is not None:
            remaining = self._interval - (self._monotonic() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._monotonic()


def get(  # noqa: PLR0913 - keyword-only request options, all optional
    client: httpx.Client,
    url: str,
    *,
    source: str,
    params: Mapping[str, str | int] | None = None,
    headers: Mapping[str, str] | None = None,
    throttle: Throttle | None = None,
) -> httpx.Response:
    """GET a URL, turning every transport failure and non-2xx status into one error type.

    With a throttle, `429` and `503` answers are retried after the delay the
    throttle decides (the server's `Retry-After` when given).

    Args:
        client: Injected HTTP client.
        url: Target URL.
        source: Source name, for error messages.
        params: Query parameters.
        headers: Extra request headers.
        throttle: Source pacing; enables retries on rate limiting.

    Returns:
        The successful response.

    Raises:
        SourceUnavailableError: On network errors, timeouts and non-2xx statuses
            (after retries are exhausted, for retryable ones).
    """
    attempt = 0
    while True:
        try:
            response = client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(source, f"request to {url} failed: {exc}") from exc
        if response.is_success:
            return response
        delay = (
            throttle.retry_delay(attempt, response.headers.get("Retry-After"))
            if throttle is not None and response.status_code in RETRYABLE_STATUSES
            else None
        )
        if throttle is None or delay is None:
            message = f"HTTP {response.status_code} from {url}"
            raise SourceUnavailableError(source, message, response.status_code)
        logger.info("%s: HTTP %d, retrying in %.0f s", source, response.status_code, delay)
        throttle.pause(delay)
        attempt += 1


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

import httpx
import pytest

from auto_biblio.domain.errors import SourceUnavailableError
from auto_biblio.sources._http import Throttle, get


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_throttle_sleeps_remaining_interval() -> None:
    fake = FakeTime()
    throttle = Throttle(3.0, monotonic=fake.monotonic, sleep=fake.sleep)
    throttle.wait()
    fake.now = 1.0
    throttle.wait()
    fake.now = 10.0
    throttle.wait()
    assert fake.sleeps == [2.0]


def client_returning(status: int) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status)))


@pytest.mark.parametrize("status", [503, 429, 404])
def test_get_maps_error_statuses(status: int) -> None:
    with pytest.raises(SourceUnavailableError, match=str(status)):
        get(client_returning(status), "https://example.com", source="s")


def test_get_maps_transport_errors() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        message = "refused"
        raise httpx.ConnectError(message, request=request)

    client = httpx.Client(transport=httpx.MockTransport(boom))
    with pytest.raises(SourceUnavailableError, match="refused"):
        get(client, "https://example.com", source="s")


def test_get_passes_params_and_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    response = get(client, "https://e.com/x", source="s", params={"a": 1}, headers={"X-T": "v"})
    assert response.text == "ok"
    assert seen[0].url.params["a"] == "1"
    assert seen[0].headers["X-T"] == "v"


def test_unavailable_error_carries_status() -> None:
    with pytest.raises(SourceUnavailableError) as excinfo:
        get(client_returning(404), "https://example.com", source="s")
    assert excinfo.value.status_code == 404

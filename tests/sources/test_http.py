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


def scripted_client(*responses: httpx.Response) -> tuple[httpx.Client, list[httpx.Request]]:
    queue = list(responses)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def make_throttle(fake: FakeTime, max_retries: int = 3) -> Throttle:
    return Throttle(0, monotonic=fake.monotonic, sleep=fake.sleep, max_retries=max_retries)


def test_get_retries_using_retry_after() -> None:
    fake = FakeTime()
    client, seen = scripted_client(
        httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, text="ok")
    )
    response = get(client, "https://e.com", source="s", throttle=make_throttle(fake))
    assert response.text == "ok"
    assert len(seen) == 2
    assert fake.sleeps == [7.0]


def test_get_backs_off_exponentially_without_retry_after() -> None:
    fake = FakeTime()
    client, _ = scripted_client(
        httpx.Response(503), httpx.Response(503), httpx.Response(200, text="ok")
    )
    get(client, "https://e.com", source="s", throttle=make_throttle(fake))
    assert fake.sleeps == [10.0, 20.0]


def test_get_caps_retry_after() -> None:
    fake = FakeTime()
    client, _ = scripted_client(
        httpx.Response(429, headers={"Retry-After": "3600"}), httpx.Response(200)
    )
    get(client, "https://e.com", source="s", throttle=make_throttle(fake))
    assert fake.sleeps == [120.0]


def test_get_gives_up_after_max_retries() -> None:
    fake = FakeTime()
    client, seen = scripted_client(httpx.Response(429))
    with pytest.raises(SourceUnavailableError, match="429"):
        get(client, "https://e.com", source="s", throttle=make_throttle(fake, max_retries=2))
    assert len(seen) == 3


def test_get_does_not_retry_other_errors() -> None:
    fake = FakeTime()
    client, seen = scripted_client(httpx.Response(404))
    with pytest.raises(SourceUnavailableError):
        get(client, "https://e.com", source="s", throttle=make_throttle(fake))
    assert len(seen) == 1
    assert fake.sleeps == []

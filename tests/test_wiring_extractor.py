from pathlib import Path

import httpx
from builders import make_item

from auto_biblio.config import Settings
from auto_biblio.wiring import real_extractor


def test_real_extractor_falls_back_offline(tmp_path: Path) -> None:
    def refuse(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(refuse))
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue] - pydantic-settings init option
    extracted = real_extractor(settings, client, tmp_path).extract(
        make_item(item_id="arxiv:1"), 1000
    )
    assert extracted.source == "abstract"

from auto_biblio.domain.errors import (
    AutoBiblioError,
    ConfigError,
    SourcePayloadError,
    SourceUnavailableError,
)


def test_config_error_str() -> None:
    with_field = ConfigError("config/sources.yaml", "sources.2.min_stars", "bad int")
    without_field = ConfigError("config/profile.yaml", None, "file not found")
    assert str(with_field) == "config/sources.yaml: sources.2.min_stars: bad int"
    assert str(without_field) == "config/profile.yaml: file not found"
    assert isinstance(with_field, AutoBiblioError)


def test_source_unavailable_carries_source() -> None:
    err = SourceUnavailableError("hn", "HTTP 503")
    assert err.source == "hn"
    assert str(err) == "hn: HTTP 503"


def test_payload_excerpt_truncated() -> None:
    err = SourcePayloadError("arxiv", "bad payload", "x" * 20_000)
    assert err.source == "arxiv"
    assert len(err.payload_excerpt) == 10_000
    assert str(err) == "arxiv: bad payload"

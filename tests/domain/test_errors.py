from auto_biblio.domain.errors import (
    AutoBiblioError,
    BudgetExhaustedError,
    ChainExhaustedError,
    ConfigError,
    ContextFetchError,
    EmbeddingError,
    FeedbackParseError,
    LLMOutputInvalidError,
    MailDeliveryError,
    ProviderQuotaError,
    ProviderUnavailableError,
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


def test_model_errors_carry_model() -> None:
    for cls in (ProviderQuotaError, ProviderUnavailableError, LLMOutputInvalidError):
        err = cls("google:flash", "boom")
        assert err.model_id == "google:flash"
        assert str(err) == "google:flash: boom"


def test_chain_exhausted_lists_attempts() -> None:
    err = ChainExhaustedError("triage", ("a: quota", "b: down"))
    assert err.attempts == ("a: quota", "b: down")
    assert str(err) == "every model of the 'triage' chain failed: a: quota; b: down"


def test_budget_exhausted_str() -> None:
    err = BudgetExhaustedError("usd", 0.02, 0.01)
    assert err.limit == "usd"
    assert str(err) == "usd budget exhausted: needs 0.02, 0.01 left"


def test_simple_errors() -> None:
    assert str(ContextFetchError("https://x", "HTTP 404")) == "https://x: HTTP 404"
    assert ContextFetchError("https://x", "e").url == "https://x"
    assert str(FeedbackParseError("issue#3", "bad title")) == "issue#3: bad title"
    assert FeedbackParseError("issue#3", "x").origin == "issue#3"
    assert str(EmbeddingError("no model")) == "no model"
    assert str(MailDeliveryError("smtp down")) == "smtp down"

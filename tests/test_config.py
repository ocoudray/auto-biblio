import pytest
from pydantic import ValidationError

from auto_biblio.config import Settings


def load_settings() -> Settings:
    # `_env_file` is a pydantic-settings init option that pyright cannot see in the
    # field-based signature; passing None keeps a developer's local `.env` out of the tests.
    return Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_default_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_BIBLIO_LOG_LEVEL", raising=False)
    assert load_settings().log_level == "INFO"


def test_log_level_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_BIBLIO_LOG_LEVEL", "DEBUG")
    assert load_settings().log_level == "DEBUG"


def test_invalid_log_level_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_BIBLIO_LOG_LEVEL", "LOUD")
    with pytest.raises(ValidationError):
        load_settings()


def test_github_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_BIBLIO_GITHUB_TOKEN", "ghp_test")
    token = load_settings().github_token
    assert token is not None
    assert token.get_secret_value() == "ghp_test"


def test_collection_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_BIBLIO_DATA_DIR", raising=False)
    settings = load_settings()
    assert settings.http_timeout_s == 30.0
    assert settings.user_agent.startswith("auto-biblio/")

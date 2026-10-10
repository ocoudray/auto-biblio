from pathlib import Path

import pytest
from fakes import FakeRunner, ignore_fallback
from pydantic import SecretStr

from auto_biblio.config import Settings
from auto_biblio.domain.budget import BudgetLedger
from auto_biblio.domain.errors import ConfigError
from auto_biblio.llm.cached import CachedLLM
from auto_biblio.publish.smtp import SmtpMailSender
from auto_biblio.repo_config.llm import Budget, LLMConfig
from auto_biblio.wiring import llm_factory, real_mail_sender, usable_llm_config

CONFIG = LLMConfig.model_validate(
    {
        "models": {
            "flash": {
                "id": "google:gemini-x",
                "input_usd_per_mtok": 0,
                "output_usd_per_mtok": 0,
                "batch_size": 20,
            },
            "haiku": {
                "id": "anthropic:claude-x",
                "input_usd_per_mtok": 1,
                "output_usd_per_mtok": 5,
                "batch_size": 15,
            },
            "local": {
                "id": "ollama:qwen",
                "input_usd_per_mtok": 0,
                "output_usd_per_mtok": 0,
                "batch_size": 5,
            },
        },
        "chains": {"triage": ["flash", "haiku"]},
        "weekly_budget": {"usd": 1, "tokens": 100_000},
    }
)


def settings(**values: object) -> Settings:
    # `_env_file=None` keeps a developer's `.env` out of the tests (pydantic-settings option).
    return Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]


def test_missing_key_drops_model(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("AUTO_BIBLIO_GEMINI_API_KEY", raising=False)
    usable = usable_llm_config(CONFIG, settings(anthropic_api_key=SecretStr("a")))
    assert usable.chains["triage"] == ("haiku",)
    assert "no API key for flash" in caplog.text


def test_keyless_providers_kept() -> None:
    config = CONFIG.model_copy(update={"chains": {"triage": ("local",)}})
    assert usable_llm_config(config, settings()).chains["triage"] == ("local",)


def test_no_usable_model_is_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("AUTO_BIBLIO_GEMINI_API_KEY", "AUTO_BIBLIO_ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError, match=r"chains\.triage"):
        usable_llm_config(CONFIG, settings())


def test_llm_factory_builds_cached_chain(tmp_path: Path) -> None:
    build = llm_factory(FakeRunner(), CONFIG, tmp_path)
    llm = build(BudgetLedger(Budget(usd=1, tokens=1000)), ignore_fallback)
    assert isinstance(llm, CachedLLM)


def test_real_mail_sender() -> None:
    assert real_mail_sender(settings()) is None
    sender = real_mail_sender(settings(smtp_user="me@gmail.com", smtp_password=SecretStr("p")))
    assert isinstance(sender, SmtpMailSender)


def test_empty_key_counts_as_missing() -> None:
    # An unset GitHub secret reaches the workflow as an empty variable.
    usable = usable_llm_config(
        CONFIG, settings(gemini_api_key=SecretStr(""), anthropic_api_key=SecretStr("a"))
    )
    assert usable.chains["triage"] == ("haiku",)

import pytest
from pydantic import ValidationError

from auto_biblio.domain.errors import ConfigError
from auto_biblio.repo_config.llm import LLMConfig

MODELS = {
    "flash": {
        "id": "test:flash",
        "input_usd_per_mtok": 0,
        "output_usd_per_mtok": 0,
        "batch_size": 20,
    },
    "haiku": {
        "id": "test:haiku",
        "input_usd_per_mtok": 1,
        "output_usd_per_mtok": 5,
        "batch_size": 15,
    },
}


def test_llm_config_valid() -> None:
    cfg = LLMConfig.model_validate(
        {
            "models": MODELS,
            "chains": {"triage": ["flash", "haiku"]},
            "weekly_budget": {"usd": 0.5, "tokens": 300_000},
        }
    )
    assert cfg.chain("triage")[1].id == "test:haiku"
    assert cfg.models["flash"].max_output_tokens == 4096


def test_llm_chain_unknown_model_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown model"):
        LLMConfig.model_validate(
            {
                "models": MODELS,
                "chains": {"triage": ["flash", "opus"]},
                "weekly_budget": {"usd": 0.5, "tokens": 1},
            }
        )


def test_llm_empty_chain_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMConfig.model_validate(
            {"models": MODELS, "chains": {"triage": []}, "weekly_budget": {"usd": 0, "tokens": 0}}
        )


def test_llm_negative_price_rejected() -> None:
    bad = {"x": {**MODELS["flash"], "input_usd_per_mtok": -1}}
    with pytest.raises(ValidationError):
        LLMConfig.model_validate(
            {"models": bad, "chains": {"triage": ["x"]}, "weekly_budget": {"usd": 0, "tokens": 0}}
        )


def test_model_cost() -> None:
    cfg = LLMConfig.model_validate(
        {
            "models": MODELS,
            "chains": {"triage": ["flash"]},
            "weekly_budget": {"usd": 0, "tokens": 0},
        }
    )
    haiku = cfg.models["haiku"]
    assert haiku.cost_usd(1_000_000, 200_000) == 2.0
    assert not haiku.is_free
    assert cfg.models["flash"].is_free


def test_role_chain_missing_is_config_error() -> None:
    # A v0.3 llm.yaml (triage only) still loads; only the steps needing other roles fail.
    cfg = LLMConfig.model_validate(
        {
            "models": MODELS,
            "chains": {"triage": ["flash"]},
            "weekly_budget": {"usd": 0, "tokens": 0},
        }
    )
    cfg.require("triage")
    with pytest.raises(ConfigError, match="deep_analysis, synthesis"):
        cfg.require("triage", "deep_analysis", "synthesis")
    with pytest.raises(ConfigError, match="short_note"):
        cfg.chain("short_note")


def test_model_call_tokens_and_tpm() -> None:
    spec = LLMConfig.model_validate(
        {
            "models": {**MODELS, "gemma": {**MODELS["flash"], "id": "t:g", "tpm": 16_000}},
            "chains": {"triage": ["gemma"]},
            "weekly_budget": {"usd": 0, "tokens": 1},
        }
    ).models["gemma"]
    assert spec.call_tokens(4_000) == 1_000 + spec.max_output_tokens
    assert spec.fits(4_000)
    assert not spec.fits(60_000)
    assert (
        LLMConfig.model_validate(
            {
                "models": MODELS,
                "chains": {"triage": ["flash"]},
                "weekly_budget": {"usd": 0, "tokens": 1},
            }
        )
        .models["flash"]
        .fits(10_000_000)
    )

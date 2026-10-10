"""Composition root: builds the real implementations of the external boundaries."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai.models import Model

from auto_biblio.config import Settings
from auto_biblio.domain.budget import BudgetLedger
from auto_biblio.domain.errors import ConfigError
from auto_biblio.embeddings import Embedder
from auto_biblio.llm import ModelRunner, StructuredLLM
from auto_biblio.llm.budgeted import BudgetedRunner
from auto_biblio.llm.cached import CachedLLM
from auto_biblio.llm.chain import FallbackHook, ModelChain
from auto_biblio.llm.pydantic_ai import PydanticAIRunner
from auto_biblio.publish import MailSender
from auto_biblio.publish.smtp import SmtpMailSender
from auto_biblio.repo_config.llm import LLMConfig, ModelSpec
from auto_biblio.repo_config.loader import LLM_PATH
from auto_biblio.stages.triage import LLMFactory
from auto_biblio.store.llm_cache import LLMCacheStore

logger = logging.getLogger(__name__)


def _api_key(provider: str, settings: Settings) -> str | None:
    keys = {"google": settings.gemini_api_key, "anthropic": settings.anthropic_api_key}
    secret = keys.get(provider)
    # An unset GitHub secret reaches the workflow as an empty variable: treat it as missing.
    value = secret.get_secret_value() if secret is not None else ""
    return value or None


def _callable(spec: ModelSpec, settings: Settings) -> bool:
    # Providers we hold keys for need one; any other provider (e.g. a local server) does not.
    provider = _provider(spec)
    return provider not in KEYED_PROVIDERS or _api_key(provider, settings) is not None


KEYED_PROVIDERS = frozenset({"google", "anthropic"})


def usable_llm_config(config: LLMConfig, settings: Settings) -> LLMConfig:
    """Drop from the chains the models whose provider key is missing.

    Args:
        config: The configured catalogue and chains.
        settings: Where API keys come from.

    Returns:
        The configuration restricted to callable models.

    Raises:
        ConfigError: If a chain has no callable model left.
    """
    chains: dict[str, tuple[str, ...]] = {}
    for role, names in config.chains.items():
        kept = tuple(n for n in names if _callable(config.models[n], settings))
        for dropped in sorted(set(names) - set(kept)):
            logger.warning("no API key for %s: dropped from the %s chain", dropped, role)
        if not kept:
            msg = f"no model of the {role!r} chain has an API key"
            raise ConfigError(LLM_PATH.as_posix(), f"chains.{role}", msg)
        chains[role] = kept
    return config.model_copy(update={"chains": chains})


def _provider(spec: ModelSpec) -> str:
    return spec.id.split(":", 1)[0]


def model_for(spec: ModelSpec, settings: Settings) -> Model:  # pragma: no cover - real providers
    """Build the pydantic-ai model of a spec, with its credentials.

    Args:
        spec: The model.
        settings: Where API keys come from.

    Returns:
        The model.

    Raises:
        ConfigError: If the provider is not supported.
    """
    from pydantic_ai.models.anthropic import AnthropicModel  # noqa: PLC0415 - lazy provider SDKs
    from pydantic_ai.models.google import GoogleModel  # noqa: PLC0415
    from pydantic_ai.providers.anthropic import AnthropicProvider  # noqa: PLC0415
    from pydantic_ai.providers.google import GoogleProvider  # noqa: PLC0415

    provider, name = spec.id.split(":", 1)
    key = _api_key(provider, settings)
    if provider == "google":
        return GoogleModel(name, provider=GoogleProvider(api_key=key))
    if provider == "anthropic":
        return AnthropicModel(name, provider=AnthropicProvider(api_key=key))
    msg = f"unsupported provider {provider!r} (supported: google, anthropic)"
    raise ConfigError(LLM_PATH.as_posix(), "models", msg)


def llm_factory(runner: ModelRunner, config: LLMConfig, state_dir: Path) -> LLMFactory:
    """Assemble the LLM of a run: cache, then chain, then budget, then the provider call.

    Args:
        runner: Calls one model.
        config: The usable LLM configuration.
        state_dir: The data repository's `state/` directory (LLM cache).

    Returns:
        A factory taking the run's ledger and fallback hook.
    """

    def build(ledger: BudgetLedger, on_fallback: FallbackHook) -> StructuredLLM:
        chain = ModelChain(BudgetedRunner(runner, ledger), config, on_fallback)
        return CachedLLM(chain, LLMCacheStore(state_dir), config)

    return build


@dataclass(frozen=True)
class Services:
    """The external boundaries the CLI needs beyond HTTP; replaced by fakes in tests."""

    embedder: Callable[[Settings], Embedder]
    model_runner: Callable[[Settings], ModelRunner]
    mail_sender: Callable[[Settings], MailSender | None]


def _real_embedder(_settings: Settings) -> Embedder:  # pragma: no cover - loads the model
    from auto_biblio.embeddings.fastembed import FastEmbedder  # noqa: PLC0415 - heavy import

    return FastEmbedder.load()


def _real_runner(settings: Settings) -> ModelRunner:  # pragma: no cover - real providers
    return PydanticAIRunner(lambda spec: model_for(spec, settings))


def real_mail_sender(settings: Settings) -> MailSender | None:
    """Build the SMTP sender when credentials are configured.

    Args:
        settings: SMTP settings.

    Returns:
        The sender, or None without user or password.
    """
    if settings.smtp_user is None or settings.smtp_password is None:
        return None
    return SmtpMailSender(
        settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password
    )


REAL_SERVICES = Services(
    embedder=_real_embedder, model_runner=_real_runner, mail_sender=real_mail_sender
)

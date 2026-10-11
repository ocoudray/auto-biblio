"""Domain exceptions raised across the package."""

from typing import Literal

PAYLOAD_EXCERPT_MAX = 10_000


class AutoBiblioError(Exception):
    """Base class of every error raised on purpose by auto-biblio."""


class ConfigError(AutoBiblioError):
    """A configuration file is missing, unreadable or invalid."""

    def __init__(self, path: str, field: str | None, message: str) -> None:
        """Build the error.

        Args:
            path: Path of the faulty file, relative to the data repository.
            field: Dotted location of the faulty field, if known.
            message: What is wrong.
        """
        self.path = path
        self.field = field
        prefix = f"{path}: {field}" if field else path
        super().__init__(f"{prefix}: {message}")


class SourceUnavailableError(AutoBiblioError):
    """A source could not be reached (network error, timeout, non-2xx status)."""

    def __init__(self, source: str, message: str, status_code: int | None = None) -> None:
        """Build the error.

        Args:
            source: Name of the source, as configured.
            message: What went wrong.
            status_code: HTTP status, when the source answered with one.
        """
        self.source = source
        self.status_code = status_code
        super().__init__(f"{source}: {message}")


class SourcePayloadError(AutoBiblioError):
    """A source answered with a payload that does not match its expected format."""

    def __init__(self, source: str, message: str, payload_excerpt: str = "") -> None:
        """Build the error.

        Args:
            source: Name of the source, as configured.
            message: What is wrong with the payload.
            payload_excerpt: Raw payload, kept (truncated) for quarantine.
        """
        self.source = source
        self.payload_excerpt = payload_excerpt[:PAYLOAD_EXCERPT_MAX]
        super().__init__(f"{source}: {message}")


class EmbeddingError(AutoBiblioError):
    """The local embedding model could not be loaded or failed to embed."""


class _ModelError(AutoBiblioError):
    def __init__(self, model_id: str, message: str) -> None:
        self.model_id = model_id
        super().__init__(f"{model_id}: {message}")


class ProviderQuotaError(_ModelError):
    """The provider refused the call because a quota or rate limit was reached."""


class ProviderUnavailableError(_ModelError):
    """The provider could not be reached or answered with an error."""


class LLMOutputInvalidError(_ModelError):
    """The model answered, but its output does not match the expected structure."""


class ChainExhaustedError(AutoBiblioError):
    """Every model of a role's chain failed."""

    def __init__(self, role: str, attempts: tuple[str, ...]) -> None:
        """Build the error.

        Args:
            role: The role whose chain was exhausted.
            attempts: One line per failed model, `<model>: <reason>`.
        """
        self.role = role
        self.attempts = attempts
        super().__init__(f"every model of the {role!r} chain failed: {'; '.join(attempts)}")


class BudgetExhaustedError(AutoBiblioError):
    """A call would exceed the weekly budget."""

    def __init__(self, limit: Literal["usd", "tokens"], needed: float, remaining: float) -> None:
        """Build the error.

        Args:
            limit: Which cap would be exceeded.
            needed: Estimated cost of the call, in the unit of the cap.
            remaining: What is left of the cap.
        """
        self.limit = limit
        self.needed = needed
        self.remaining = remaining
        super().__init__(f"{limit} budget exhausted: needs {needed:g}, {remaining:g} left")


class ContextFetchError(AutoBiblioError):
    """No context snippet could be fetched for an item."""

    def __init__(self, url: str, message: str) -> None:
        """Build the error.

        Args:
            url: The page that was fetched.
            message: What went wrong.
        """
        self.url = url
        super().__init__(f"{url}: {message}")


class FeedbackParseError(AutoBiblioError):
    """A feedback issue does not follow the expected format."""

    def __init__(self, origin: str, message: str) -> None:
        """Build the error.

        Args:
            origin: Where the feedback came from, e.g. `issue#12`.
            message: What is wrong.
        """
        self.origin = origin
        super().__init__(f"{origin}: {message}")


class MailDeliveryError(AutoBiblioError):
    """The digest could not be sent."""


class TriageRunMissingError(AutoBiblioError):
    """No triage journal exists for the requested week."""

    def __init__(self, week: str | None) -> None:
        """Build the error.

        Args:
            week: The requested week, or None for "the latest one".
        """
        self.week = week
        what = f"week {week}" if week else "any week"
        super().__init__(f"no triage journal for {what}: run `auto-biblio triage` first")


class KBFormatError(AutoBiblioError):
    """A knowledge base file cannot be read back."""

    def __init__(self, origin: str, message: str) -> None:
        """Build the error.

        Args:
            origin: The file, relative to the knowledge base.
            message: What is wrong.
        """
        self.origin = origin
        super().__init__(f"{origin}: {message}")


class ExtractionError(AutoBiblioError):
    """No full text could be extracted for an item."""

    def __init__(self, url: str, message: str) -> None:
        """Build the error.

        Args:
            url: What was fetched.
            message: What went wrong.
        """
        self.url = url
        super().__init__(f"{url}: {message}")

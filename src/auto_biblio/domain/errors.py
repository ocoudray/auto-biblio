"""Domain exceptions raised across the package."""

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

    def __init__(self, source: str, message: str) -> None:
        """Build the error.

        Args:
            source: Name of the source, as configured.
            message: What went wrong.
        """
        self.source = source
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

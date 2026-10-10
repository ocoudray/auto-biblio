"""Source connectors: fetch raw content from the outside world and normalize it to items."""

from datetime import datetime
from typing import Protocol

from auto_biblio.domain.models import SourceBatch


class Source(Protocol):
    """A configured source instance that can be polled for new content."""

    @property
    def name(self) -> str:
        """Configured name of this source instance."""
        ...

    def fetch(self, since: datetime) -> SourceBatch:
        """Fetch what the source published since a point in time.

        Args:
            since: Aware UTC lower bound (sources may return a little more).

        Returns:
            Normalized items and signals.

        Raises:
            SourceUnavailableError: The source could not be reached.
            SourcePayloadError: The source answered with an unexpected payload.
        """
        ...

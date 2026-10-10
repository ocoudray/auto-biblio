"""Publication of the weekly digest."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class Mail(BaseModel):
    """A ready-to-send message, with HTML and plain-text bodies."""

    model_config = ConfigDict(frozen=True)

    subject: str
    html: str
    text: str
    to: str


class MailSender(Protocol):
    """Sends a mail."""

    def send(self, mail: Mail) -> None:
        """Send a mail.

        Args:
            mail: The message.
        """
        ...

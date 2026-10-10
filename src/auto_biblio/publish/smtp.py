"""SMTP delivery of the digest (Gmail with an app password by default)."""

import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from types import TracebackType
from typing import Protocol, Self

from pydantic import SecretStr

from auto_biblio.domain.errors import MailDeliveryError
from auto_biblio.publish import Mail


class SmtpSession(Protocol):
    """The part of `smtplib.SMTP` used to send a message."""

    def __enter__(self) -> Self:
        """Open the session."""
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the session."""
        ...

    def login(self, user: str, password: str) -> object:
        """Authenticate."""
        ...

    def send_message(self, msg: EmailMessage) -> object:
        """Send a message."""
        ...


type SmtpFactory = Callable[[str, int], SmtpSession]


class SmtpMailSender:
    """Sends mails over SMTP with TLS."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: SecretStr,
        smtp_factory: SmtpFactory = smtplib.SMTP_SSL,
    ) -> None:
        """Build the sender.

        Args:
            host: SMTP server.
            port: SMTP port (465 for implicit TLS).
            user: Login, also used as sender address.
            password: Password (an application password for Gmail).
            smtp_factory: Opens the connection (injected for tests).
        """
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._factory = smtp_factory

    def send(self, mail: Mail) -> None:
        """Send a mail.

        Args:
            mail: The message.

        Raises:
            MailDeliveryError: If the server cannot be reached or refuses the message.
        """
        message = EmailMessage()
        message["Subject"] = mail.subject
        message["From"] = self._user
        message["To"] = mail.to
        message.set_content(mail.text)
        message.add_alternative(mail.html, subtype="html")
        try:
            with self._factory(self._host, self._port) as smtp:
                smtp.login(self._user, self._password.get_secret_value())
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            msg = f"cannot send the digest through {self._host}:{self._port}: {exc}"
            raise MailDeliveryError(msg) from exc

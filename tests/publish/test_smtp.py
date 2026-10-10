import smtplib
from email.message import EmailMessage
from types import TracebackType
from typing import Self

import pytest
from pydantic import SecretStr

from auto_biblio.domain.errors import MailDeliveryError
from auto_biblio.publish import Mail
from auto_biblio.publish.smtp import SmtpMailSender

MAIL = Mail(subject="S", html="<p>h</p>", text="t", to="me@example.com")


class FakeSession:
    def __init__(self) -> None:
        self.logins: list[tuple[str, str]] = []
        self.sent: list[EmailMessage] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def login(self, user: str, password: str) -> object:
        self.logins.append((user, password))
        return None

    def send_message(self, msg: EmailMessage) -> object:
        self.sent.append(msg)
        return None


def test_send_builds_multipart_message() -> None:
    session = FakeSession()
    opened: list[tuple[str, int]] = []

    def factory(host: str, port: int) -> FakeSession:
        opened.append((host, port))
        return session

    SmtpMailSender("smtp.example", 465, "me@gmail.com", SecretStr("app-pass"), factory).send(MAIL)
    assert opened == [("smtp.example", 465)]
    assert session.logins == [("me@gmail.com", "app-pass")]
    message = session.sent[0]
    assert message["To"] == "me@example.com"
    assert message["From"] == "me@gmail.com"
    assert message["Subject"] == "S"
    assert message.is_multipart()


def test_smtp_error_wrapped() -> None:
    def refuse(_host: str, _port: int) -> FakeSession:
        raise smtplib.SMTPConnectError(421, "busy")

    sender = SmtpMailSender("smtp.example", 465, "me@gmail.com", SecretStr("x"), refuse)
    with pytest.raises(MailDeliveryError, match=r"smtp\.example:465"):
        sender.send(MAIL)

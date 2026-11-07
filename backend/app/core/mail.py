"""Outgoing e-mail.

`get_mailer()` is a FastAPI dependency (and a plain function for the CLI) returning the
configured backend:

* `SmtpMailer`    -- real delivery through SMTP (`SMTP_HOST` set). In development this is
                     the Mailpit container; in production any SMTP relay.
* `LoggingMailer` -- `SMTP_HOST` empty: messages are written to the log instead of being
                     sent, so the application keeps working without a mail server.
* `InMemoryMailer`-- keeps messages in a list; used by the test-suite.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class MailDeliveryError(RuntimeError):
    """The message could not be handed over to the mail server."""


@dataclass(frozen=True, slots=True)
class Mail:
    to: str
    subject: str
    text: str
    html: str | None = None

    def as_message(self, sender: str) -> EmailMessage:
        message = EmailMessage()
        message["From"] = sender
        message["To"] = self.to
        message["Subject"] = self.subject
        message.set_content(self.text)
        if self.html:
            message.add_alternative(self.html, subtype="html")
        return message


class Mailer(Protocol):
    async def send(self, mail: Mail) -> None: ...


@dataclass(slots=True)
class SmtpMailer:
    host: str
    port: int
    sender: str
    user: str = ""
    password: str = ""
    starttls: bool = False
    timeout: float = 10.0

    async def send(self, mail: Mail) -> None:
        # smtplib is blocking: keep the event loop free while talking to the server.
        try:
            await asyncio.to_thread(self._deliver, mail.as_message(self.sender))
        except (OSError, smtplib.SMTPException) as exc:
            logger.error(
                "Could not send e-mail to %s via %s:%s: %s", mail.to, self.host, self.port, exc
            )
            raise MailDeliveryError(str(exc)) from exc

    def _deliver(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(message)


@dataclass(slots=True)
class LoggingMailer:
    """No mail server configured: the message (links included) goes to the log."""

    sender: str = ""

    async def send(self, mail: Mail) -> None:
        logger.info(
            "E-mail not sent (SMTP_HOST is empty)\nTo: %s\nSubject: %s\n\n%s",
            mail.to,
            mail.subject,
            mail.text,
        )


@dataclass(slots=True)
class InMemoryMailer:
    """Collects messages instead of sending them (test-suite)."""

    outbox: list[Mail] = field(default_factory=list)

    async def send(self, mail: Mail) -> None:
        self.outbox.append(mail)


def build_mailer(settings: Settings) -> Mailer:
    if not settings.mail_enabled:
        return LoggingMailer(sender=settings.mail_from)
    return SmtpMailer(
        host=settings.smtp_host,
        port=settings.smtp_port,
        sender=settings.mail_from,
        user=settings.smtp_user,
        password=settings.smtp_password,
        starttls=settings.smtp_starttls,
        timeout=settings.smtp_timeout,
    )


_mailer: Mailer | None = None


def get_mailer() -> Mailer:
    """FastAPI dependency: the process-wide mailer built from the settings."""
    global _mailer
    if _mailer is None:
        _mailer = build_mailer(get_settings())
    return _mailer

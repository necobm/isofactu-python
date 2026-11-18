"""ORM entities of the AI module."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.accounts.models import User, utcnow
from app.core.database import Base


class AiSettings(Base):
    """The AI vendor a tenant reads its received invoices with (one row per account).

    The API key is stored encrypted (``app.core.crypto``) and never leaves the server. The
    other fields are not secret: Azure needs the resource endpoint, API version and
    deployment; Bedrock the AWS region. They are empty for the other vendors.
    """

    __tablename__ = "ai_settings"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), init=False, unique=True
    )
    owner: Mapped[User] = relationship(repr=False)
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(200))
    api_key_encrypted: Mapped[str] = mapped_column(Text, repr=False)
    endpoint: Mapped[str] = mapped_column(String(255), default="")
    api_version: Mapped[str] = mapped_column(String(50), default="")
    deployment: Mapped[str] = mapped_column(String(100), default="")
    region: Mapped[str] = mapped_column(String(30), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default_factory=utcnow, onupdate=utcnow
    )

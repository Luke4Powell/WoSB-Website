from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GuildPortOrder(Base):
    __tablename__ = "guild_port_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    content: Mapped[str] = mapped_column(Text(), default="")
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RosterAssignment(Base):
    """One row per player per roster board (scope + guild slug + rate); slot is A or B."""

    __tablename__ = "roster_assignments"
    __table_args__ = (
        UniqueConstraint("scope", "guild_slug", "rate", "user_id", name="uq_roster_board_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16), index=True)
    guild_slug: Mapped[str] = mapped_column(String(32), default="", index=True)
    rate: Mapped[int] = mapped_column(Integer(), index=True)
    slot: Mapped[str] = mapped_column(String(1))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now
    )

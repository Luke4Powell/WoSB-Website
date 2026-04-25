from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PortBattleSession(Base):
    """Organizer-defined port fight: one side size, primary guild (defender), ship mix."""

    __tablename__ = "port_battle_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16), index=True)
    guild_slug: Mapped[str] = mapped_column(String(32), default="", index=True)
    primary_guild_slug: Mapped[str] = mapped_column(String(32), index=True)

    port_name: Mapped[str] = mapped_column(String(200))
    rate_text: Mapped[str] = mapped_column(String(64))
    rate_num: Mapped[int] = mapped_column(Integer(), index=True)
    per_side: Mapped[int] = mapped_column(Integer())
    pvp_label: Mapped[str] = mapped_column(String(32), default="")

    ship_mix_json: Mapped[str] = mapped_column(Text(), default="[]")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )


class PortBattleReady(Base):
    """Member readied for a session with one ship instance from their fleet."""

    __tablename__ = "port_battle_ready"
    __table_args__ = (UniqueConstraint("session_id", "user_id", name="uq_port_battle_ready_session_user"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("port_battle_sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    instance_id: Mapped[str] = mapped_column(String(128))
    ship_id: Mapped[str] = mapped_column(String(128))
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class PortBattleLineupSlot(Base):
    """One slot on the defending roster (size = per_side)."""

    __tablename__ = "port_battle_lineup_slots"
    __table_args__ = (UniqueConstraint("session_id", "slot_index", name="uq_port_battle_lineup_slot"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("port_battle_sessions.id", ondelete="CASCADE"), index=True
    )
    slot_index: Mapped[int] = mapped_column(Integer(), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

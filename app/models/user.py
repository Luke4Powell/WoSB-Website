from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    discord_id: Mapped[int] = mapped_column(BigInteger(), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(128))
    global_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_admiral: Mapped[bool] = mapped_column(Boolean(), default=False)
    is_leader: Mapped[bool] = mapped_column(Boolean(), default=False)
    is_alliance_leader: Mapped[bool] = mapped_column(Boolean(), default=False)
    is_officer: Mapped[bool] = mapped_column(Boolean(), default=False)
    is_member: Mapped[bool] = mapped_column(Boolean(), default=False)

    home_guild_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ships_json: Mapped[str | None] = mapped_column(Text(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )

    def can_read_all_profiles(self) -> bool:
        return self.is_admiral or self.is_leader or self.is_alliance_leader

    def can_edit_guild_rosters(self) -> bool:
        return self.is_admiral or self.is_leader

    def can_edit_alliance_team(self) -> bool:
        return self.is_alliance_leader

    def can_manage_roster_assignments(self) -> bool:
        return bool(
            self.is_officer or self.is_admiral or self.is_leader or self.is_alliance_leader
        )

    def can_access_member_features(self) -> bool:
        return bool(
            self.is_member or self.is_officer or self.is_admiral or self.is_leader or self.is_alliance_leader
        )

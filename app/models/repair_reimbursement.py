from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RepairReimbursementRequest(Base):
    __tablename__ = "repair_reimbursement_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    qty_canvas: Mapped[int] = mapped_column(Integer(), default=0)
    qty_beams: Mapped[int] = mapped_column(Integer(), default=0)
    qty_bulkheads: Mapped[int] = mapped_column(Integer(), default=0)
    qty_bronze: Mapped[int] = mapped_column(Integer(), default=0)
    qty_plates: Mapped[int] = mapped_column(Integer(), default=0)
    qty_bp_fragment: Mapped[int] = mapped_column(Integer(), default=0)

    gold_repair_cost: Mapped[int] = mapped_column(Integer(), default=0)
    material_payout_gold: Mapped[int] = mapped_column(Integer(), default=0)

    fight_description: Mapped[str] = mapped_column(Text(), default="")

    submitter_guild_tag: Mapped[str] = mapped_column(String(32), default="")

    bill_image_filename: Mapped[str] = mapped_column(String(512))
    payout_proof_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )

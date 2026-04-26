from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import require_user_redirect
from app.models import RepairReimbursementRequest, User
from app.reimbursement.access import (
    can_review_reimbursement_request_for_tag,
    can_review_reimbursement_requests,
    can_submit_reimbursement,
    reimbursement_enabled_guild_tags,
)
from app.reimbursement.material_rates import RATE_BY_KEY, REIMBURSEMENT_MATERIALS
from app.reimbursement.storage import reimbursement_upload_dir, save_reimbursement_image
from app.web_static import static_asset_version

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["repair-reimbursement"])

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _template_ctx(settings, **extra) -> dict:
    out = {
        "app_name": settings.app_name,
        "site_background_image": settings.site_background_image or None,
        "static_asset_v": static_asset_version(),
    }
    out.update(extra)
    user = out.get("user")
    if user is not None:
        from app.roster_data import default_roster_board_path

        out.setdefault("default_roster_href", default_roster_board_path(user))
    return out


def _display_name(u: User) -> str:
    return (u.global_name or u.username or "").strip() or str(u.discord_id)


def _material_payout_totals(
    *,
    qty_canvas: int,
    qty_beams: int,
    qty_bulkheads: int,
    qty_bronze: int,
    qty_plates: int,
    qty_bp_fragment: int,
) -> int:
    keys = ("canvas", "beams", "bulkheads", "bronze", "plates", "bp_fragment")
    qtys = (qty_canvas, qty_beams, qty_bulkheads, qty_bronze, qty_plates, qty_bp_fragment)
    total = 0
    for key, q in zip(keys, qtys, strict=True):
        rate = RATE_BY_KEY.get(key, 0)
        total += max(0, q) * rate
    return total


def _bill_path(fname: str) -> Path:
    return reimbursement_upload_dir(BASE_DIR) / fname


async def _get_request_or_404(db: AsyncSession, rid: int) -> RepairReimbursementRequest:
    row = await db.execute(select(RepairReimbursementRequest).where(RepairReimbursementRequest.id == rid))
    req = row.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return req


def _can_view_request_images(user: User, req: RepairReimbursementRequest) -> bool:
    if req.user_id == user.id:
        return True
    return can_review_reimbursement_request_for_tag(user, req.submitter_guild_tag)


@router.get("/tools/repair-reimbursement", response_class=HTMLResponse)
async def repair_reimbursement_page(
    request: Request,
    user: Annotated[User, Depends(require_user_redirect)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    settings = get_settings()
    submit_error_message = request.session.pop("reimb_submit_error", None)
    mine = (
        await db.execute(
            select(RepairReimbursementRequest)
            .where(RepairReimbursementRequest.user_id == user.id)
            .order_by(RepairReimbursementRequest.created_at.desc())
        )
    ).scalars().all()

    pending_for_review: list[RepairReimbursementRequest] = []
    submitters: dict[int, User] = {}
    if can_review_reimbursement_requests(user):
        reviewer_tag = (user.home_guild_tag or "").strip().upper()
        pending_for_review = (
            await db.execute(
                select(RepairReimbursementRequest)
                .where(
                    RepairReimbursementRequest.status == "pending",
                    RepairReimbursementRequest.submitter_guild_tag == reviewer_tag,
                )
                .order_by(RepairReimbursementRequest.created_at.asc())
            )
        ).scalars().all()
        uids = {r.user_id for r in pending_for_review}
        if uids:
            rows = await db.execute(select(User).where(User.id.in_(uids)))
            for u in rows.scalars().all():
                submitters[u.id] = u

    return templates.TemplateResponse(
        request,
        "repair_reimbursement.html",
        _template_ctx(
            settings,
            user=user,
            materials=REIMBURSEMENT_MATERIALS,
            reimbursement_enabled_tags=sorted(reimbursement_enabled_guild_tags()),
            can_review=can_review_reimbursement_requests(user),
            my_requests=mine,
            pending_for_review=pending_for_review,
            submitters_by_id=submitters,
            display_name=_display_name,
            submit_error_message=submit_error_message,
        ),
    )


@router.post("/tools/repair-reimbursement/submit")
async def submit_reimbursement(
    request: Request,
    user: Annotated[User, Depends(require_user_redirect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    bill_image: UploadFile = File(...),
    fight_description: str = Form(""),
    gold_repair_cost: int = Form(0),
    qty_canvas: int = Form(0),
    qty_beams: int = Form(0),
    qty_bulkheads: int = Form(0),
    qty_bronze: int = Form(0),
    qty_plates: int = Form(0),
    qty_bp_fragment: int = Form(0),
):
    if not can_submit_reimbursement(user):
        tag = (user.home_guild_tag or "").strip()
        label = tag if tag else "Your guild"
        msg = (
            f"{label} does not currently have reimbursements setup through the Spanish Faction website."
        )
        request.session["reimb_submit_error"] = msg
        return RedirectResponse("/tools/repair-reimbursement", status_code=303)

    if not (bill_image.filename or "").strip():
        raise HTTPException(status_code=400, detail="Repair bill screenshot is required.")

    fight_text = (fight_description or "").strip()
    if len(fight_text) < 3:
        raise HTTPException(
            status_code=400,
            detail="Fight / battle description is required (at least a few characters).",
        )
    if len(fight_text) > 2000:
        raise HTTPException(status_code=400, detail="Fight / battle description is too long (max 2000 characters).")

    def _clamp_qty(name: str, raw: int) -> int:
        try:
            v = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Invalid quantity for {name}.") from None
        if v < 0 or v > 1_000_000:
            raise HTTPException(status_code=400, detail=f"Quantity out of range for {name}.")
        return v

    qc = _clamp_qty("canvas", qty_canvas)
    qb = _clamp_qty("beams", qty_beams)
    qk = _clamp_qty("bulkheads", qty_bulkheads)
    qz = _clamp_qty("bronze", qty_bronze)
    qp = _clamp_qty("plates", qty_plates)
    qf = _clamp_qty("BP fragment", qty_bp_fragment)

    try:
        gri = int(gold_repair_cost)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Gold repair cost is required: enter the gold amount from your repair bill.",
        ) from None
    if gri <= 0 or gri > 2_000_000_000:
        raise HTTPException(
            status_code=400,
            detail="Gold repair cost is required and must be a positive number from your repair bill.",
        )

    if qc + qb + qk + qz + qp + qf <= 0:
        raise HTTPException(status_code=400, detail="Enter at least one material quantity.")

    material_total = _material_payout_totals(
        qty_canvas=qc,
        qty_beams=qb,
        qty_bulkheads=qk,
        qty_bronze=qz,
        qty_plates=qp,
        qty_bp_fragment=qf,
    )

    guild_tag_snap = ((user.home_guild_tag or "").strip())[:32]

    req = RepairReimbursementRequest(
        user_id=user.id,
        qty_canvas=qc,
        qty_beams=qb,
        qty_bulkheads=qk,
        qty_bronze=qz,
        qty_plates=qp,
        qty_bp_fragment=qf,
        gold_repair_cost=gri,
        material_payout_gold=material_total,
        fight_description=fight_text,
        submitter_guild_tag=guild_tag_snap,
        bill_image_filename="pending",
        status="pending",
    )
    db.add(req)
    await db.flush()
    try:
        fname = await save_reimbursement_image(
            base_dir=BASE_DIR,
            request_id=req.id,
            role="bill",
            upload=bill_image,
        )
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Could not save screenshot.") from None

    req.bill_image_filename = fname
    await db.commit()
    return RedirectResponse("/tools/repair-reimbursement?submitted=1", status_code=303)


@router.get("/tools/repair-reimbursement/review/{rid}", response_class=HTMLResponse)
async def review_reimbursement_detail(
    request: Request,
    rid: int,
    user: Annotated[User, Depends(require_user_redirect)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    req = await _get_request_or_404(db, rid)
    if not can_review_reimbursement_request_for_tag(user, req.submitter_guild_tag):
        raise HTTPException(status_code=403, detail="Not allowed for this guild request.")
    if req.status != "pending":
        return RedirectResponse("/tools/repair-reimbursement", status_code=303)

    row = await db.execute(select(User).where(User.id == req.user_id))
    submitter = row.scalar_one_or_none()

    qty_rows: list[tuple[str, int, int, int]] = []
    for key, label, rate in REIMBURSEMENT_MATERIALS:
        q = int(getattr(req, f"qty_{key}", 0))
        qty_rows.append((label, rate, q, q * rate))

    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "repair_reimbursement_review.html",
        _template_ctx(
            settings,
            user=user,
            req=req,
            qty_rows=qty_rows,
            submitter=submitter,
            display_name=_display_name,
        ),
    )


@router.post("/tools/repair-reimbursement/review/{rid}/mark-paid")
async def mark_reimbursement_paid(
    rid: int,
    user: Annotated[User, Depends(require_user_redirect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    payout_image: UploadFile = File(...),
):
    req = await _get_request_or_404(db, rid)
    if not can_review_reimbursement_request_for_tag(user, req.submitter_guild_tag):
        raise HTTPException(status_code=403, detail="Not allowed for this guild request.")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="This request is not pending.")

    try:
        fname = await save_reimbursement_image(
            base_dir=BASE_DIR,
            request_id=req.id,
            role="payout",
            upload=payout_image,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    req.payout_proof_filename = fname
    req.status = "paid"
    req.paid_at = datetime.now(timezone.utc)
    req.paid_by_user_id = user.id
    await db.commit()
    return RedirectResponse("/tools/repair-reimbursement?marked_paid=1", status_code=303)


@router.get("/tools/repair-reimbursement/request/{rid}/bill")
async def serve_bill_image(
    rid: int,
    user: Annotated[User, Depends(require_user_redirect)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    req = await _get_request_or_404(db, rid)
    if not _can_view_request_images(user, req):
        raise HTTPException(status_code=403, detail="Forbidden")
    path = _bill_path(req.bill_image_filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File missing")
    suf = path.suffix.lower()
    return FileResponse(path, media_type=_MIME_BY_SUFFIX.get(suf, "application/octet-stream"))


@router.get("/tools/repair-reimbursement/request/{rid}/payout-proof")
async def serve_payout_image(
    rid: int,
    user: Annotated[User, Depends(require_user_redirect)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    req = await _get_request_or_404(db, rid)
    if not _can_view_request_images(user, req):
        raise HTTPException(status_code=403, detail="Forbidden")
    if req.status != "paid" or not req.payout_proof_filename:
        raise HTTPException(status_code=404, detail="Not available")
    path = _bill_path(req.payout_proof_filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File missing")
    suf = path.suffix.lower()
    return FileResponse(path, media_type=_MIME_BY_SUFFIX.get(suf, "application/octet-stream"))


# --- Optional: logged-out guard for image URLs (require_user_redirect already used) ---

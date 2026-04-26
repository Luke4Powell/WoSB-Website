from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import get_optional_user, require_user_redirect
from app.guild_landing_data import get_guild_landing_page, guild_discord_role_id
from app.ships_catalog import load_catalog
from app.upgrades_catalog import (
    NOT_UNLOCKED_YET_LABEL,
    STRUCTURAL_EXPANSION_LABEL,
    load_upgrades_catalog,
)
from app.consumables_catalog import load_consumables_catalog
from app.models import RepairReimbursementRequest, RosterAssignment, User
from app.models.guild_port_order import GuildPortOrder
from app.port_battle.logic import PortBattleProgramMissing, get_port_names
from app.roster_data import (
    ALLIANCE_PAGE,
    GUILD_PAGES,
    default_roster_board_path,
    get_roster_page,
    guild_choices_for_roster,
    home_tag_to_guild_slug,
    roster_board_url,
    roster_pool_eligible_user,
    user_can_open_guild_board,
)
from app.services.discord_api import fetch_members_with_role
from app.web_static import static_asset_version

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["pages"])


def _can_edit_guild_port_orders(user: User | None, guild_slug: str) -> bool:
    if user is None:
        return False
    if not (user.is_officer or user.is_leader or user.is_admiral):
        return False
    return home_tag_to_guild_slug(user.home_guild_tag) == (guild_slug or "").strip().lower()


def _roster_assignment_redirect_url(roster_view: str, rate: int, guild_slug: str | None) -> str:
    if roster_view == "guild" and guild_slug:
        return roster_board_url("guild", rate, guild_slug)
    return roster_board_url("alliance", rate)


def _template_ctx(settings, **extra) -> dict:
    out = {
        "app_name": settings.app_name,
        "site_background_image": settings.site_background_image or None,
        "static_asset_v": static_asset_version(),
    }
    out.update(extra)
    user = out.get("user")
    if user is not None:
        # Full query URL avoids relying on a bare /rosters redirect (some clients strip queries on redirects).
        out.setdefault("default_roster_href", default_roster_board_path(user))
    return out


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user: Annotated[User | None, Depends(get_optional_user)]):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "index.html",
        _template_ctx(settings, user=user, faction_guilds=GUILD_PAGES),
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: Annotated[User, Depends(require_user_redirect)]):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        _template_ctx(settings, user=user),
    )


@router.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, user: Annotated[User, Depends(require_user_redirect)]):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "profile.html",
        _template_ctx(
            settings,
            user=user,
            ships_catalog=load_catalog(),
            upgrades_catalog=load_upgrades_catalog(),
            consumables_catalog=load_consumables_catalog(),
            structural_expansion_label=STRUCTURAL_EXPANSION_LABEL,
            not_unlocked_yet_label=NOT_UNLOCKED_YET_LABEL,
        ),
    )


@router.get("/tools", response_class=HTMLResponse)
async def tools(
    request: Request,
    user: Annotated[User | None, Depends(get_optional_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)
    settings = get_settings()

    total_pending = int(
        await db.scalar(
            select(func.count())
            .select_from(RepairReimbursementRequest)
            .where(RepairReimbursementRequest.status == "pending")
        )
        or 0
    )
    my_pending = int(
        await db.scalar(
            select(func.count())
            .select_from(RepairReimbursementRequest)
            .where(
                RepairReimbursementRequest.user_id == user.id,
                RepairReimbursementRequest.status == "pending",
            )
        )
        or 0
    )
    latest_row = await db.execute(
        select(RepairReimbursementRequest.status)
        .where(RepairReimbursementRequest.user_id == user.id)
        .order_by(RepairReimbursementRequest.created_at.desc())
        .limit(1)
    )
    latest_status_raw = latest_row.scalar_one_or_none()
    raw = (str(latest_status_raw).strip().lower() if latest_status_raw is not None else "")
    reimburse_latest_kind: str | None = None
    if raw == "pending":
        reimburse_latest_kind = "pending"
    elif raw == "paid":
        reimburse_latest_kind = "paid"

    return templates.TemplateResponse(
        request,
        "tools.html",
        _template_ctx(
            settings,
            user=user,
            reimburse_total_pending=total_pending,
            reimburse_my_pending=my_pending,
            reimburse_latest_kind=reimburse_latest_kind,
        ),
    )


@router.get("/tools/port-battle", response_class=HTMLResponse)
async def port_battle_tool(request: Request, user: Annotated[User | None, Depends(get_optional_user)]):
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "port_battle.html",
        _template_ctx(settings, user=user),
    )


@router.get("/alliance")
async def alliance_home(user: Annotated[User | None, Depends(get_optional_user)]):
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)
    return RedirectResponse("/rosters", status_code=302)


@router.get("/guild/{slug}/roster")
async def guild_roster_shortcut(
    slug: str,
    user: Annotated[User | None, Depends(get_optional_user)],
):
    """Bookmarkable guild roster URL → unified /rosters board."""
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)
    guild = get_guild_landing_page(slug)
    if guild is None:
        raise HTTPException(status_code=404, detail="Unknown guild")
    gslug = str(guild.get("slug", "")).strip().lower()
    if not gslug:
        raise HTTPException(status_code=404, detail="Unknown guild")
    return RedirectResponse("/rosters", status_code=302)


@router.get("/guild/{slug}", response_class=HTMLResponse)
async def guild_landing_page(
    request: Request,
    slug: str,
    user: Annotated[User | None, Depends(get_optional_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    guild = get_guild_landing_page(slug)
    if guild is None:
        raise HTTPException(status_code=404, detail="Unknown guild")
    settings = get_settings()
    role_id = guild_discord_role_id(settings, guild["slug"])
    members: list[dict[str, str | None]] = []
    members_note: str | None = None
    if role_id:
        try:
            members = await fetch_members_with_role(settings, role_id)
        except httpx.HTTPStatusError:
            members = []
            members_note = "We could not load the crew list. Try again later."
        except Exception:
            members = []
            members_note = "Could not load the crew list right now. Try again shortly."
    else:
        members_note = "Crew list is not available on this page yet."

    members_total = len(members)
    display_members = members[:250]
    can_edit_port_orders = _can_edit_guild_port_orders(user, guild["slug"])
    existing_orders = await db.scalar(
        select(GuildPortOrder).where(GuildPortOrder.guild_slug == guild["slug"])
    )
    port_orders_text = (existing_orders.content if existing_orders else "") or str(guild.get("intro") or "")

    return templates.TemplateResponse(
        request,
        "guild_landing.html",
        _template_ctx(
            settings,
            user=user,
            guild=guild,
            members=display_members,
            members_total=members_total,
            members_note=members_note,
            port_orders_text=port_orders_text,
            can_edit_port_orders=can_edit_port_orders,
            roster_board_url=roster_board_url,
        ),
    )


@router.post("/guild/{slug}/port-orders")
async def update_guild_port_orders(
    slug: str,
    user: Annotated[User, Depends(require_user_redirect)],
    db: Annotated[AsyncSession, Depends(get_db)],
    content: str = Form(""),
):
    guild = get_guild_landing_page(slug)
    if guild is None:
        raise HTTPException(status_code=404, detail="Unknown guild")
    guild_slug = str(guild.get("slug") or "").strip().lower()
    if not guild_slug:
        raise HTTPException(status_code=404, detail="Unknown guild")
    if not _can_edit_guild_port_orders(user, guild_slug):
        raise HTTPException(status_code=403, detail="Not allowed to edit this guild's port orders")

    normalized = (content or "").strip()
    if len(normalized) > 6000:
        raise HTTPException(status_code=400, detail="Port orders are too long (max 6000 characters).")

    row = await db.scalar(select(GuildPortOrder).where(GuildPortOrder.guild_slug == guild_slug))
    if row is None:
        db.add(
            GuildPortOrder(
                guild_slug=guild_slug,
                content=normalized,
                updated_by_user_id=user.id,
            )
        )
    else:
        row.content = normalized
        row.updated_by_user_id = user.id
    await db.commit()
    return RedirectResponse(f"/guild/{guild_slug}?orders_updated=1", status_code=303)


@router.get("/rosters", response_class=HTMLResponse)
async def rosters_board(
    request: Request,
    user: Annotated[User | None, Depends(get_optional_user)],
    view: str | None = Query(None),
    guild: str | None = Query(None),
    rate: int = Query(1, ge=1, le=6),
):
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)
    _ = (view, guild)  # Kept for backward-compatible URLs; roster board is now unified.
    v = "alliance"

    try:
        port_names = get_port_names()
    except PortBattleProgramMissing:
        port_names = []

    settings = get_settings()
    ships_mix_options = load_catalog().get("ships", [])
    return templates.TemplateResponse(
        request,
        "rosters.html",
        _template_ctx(
            settings,
            user=user,
            view=v,
            rate=rate,
            roster_board_url=roster_board_url,
            can_manage_rosters=user.can_manage_roster_assignments(),
            port_names=port_names,
            ships_mix_options=ships_mix_options,
            primary_guild_choices=GUILD_PAGES,
        ),
    )


@router.post("/rosters/assignment")
async def roster_assignment_post(
    user: Annotated[User | None, Depends(get_optional_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    action: str = Form(...),
    roster_view: str = Form(..., alias="view"),
    rate: int = Form(...),
    user_id: int = Form(...),
    slot: str = Form("a"),
    guild: str = Form(""),
):
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)
    if not user.can_manage_roster_assignments():
        return RedirectResponse("/dashboard?forbidden=roster_edit", status_code=303)

    rv = (roster_view or "").strip().lower()
    if rv not in ("alliance", "guild"):
        raise HTTPException(status_code=400, detail="Invalid roster view")
    safe_rate = max(1, min(6, int(rate)))
    slot_norm = (slot or "a").strip().lower()
    if slot_norm not in ("a", "b"):
        slot_norm = "a"
    gslug = (guild or "").strip().lower()

    if rv == "guild":
        if not user_can_open_guild_board(user, gslug):
            return RedirectResponse("/dashboard?forbidden=roster", status_code=303)
        store_guild = gslug
    else:
        store_guild = ""
        gslug = ""

    act = (action or "").strip().lower()
    dest = _roster_assignment_redirect_url(rv, safe_rate, gslug or None)

    if act == "remove":
        await db.execute(
            delete(RosterAssignment).where(
                RosterAssignment.scope == rv,
                RosterAssignment.guild_slug == store_guild,
                RosterAssignment.rate == safe_rate,
                RosterAssignment.user_id == user_id,
            )
        )
        await db.commit()
        return RedirectResponse(url=dest, status_code=303)

    if act != "add":
        raise HTTPException(status_code=400, detail="Invalid action")

    target = await db.get(User, user_id)
    if target is None or not roster_pool_eligible_user(
        target, view=rv, guild_slug=gslug if rv == "guild" else None
    ):
        return RedirectResponse(url=dest, status_code=303)

    prev = await db.execute(
        select(RosterAssignment).where(
            RosterAssignment.scope == rv,
            RosterAssignment.guild_slug == store_guild,
            RosterAssignment.rate == safe_rate,
            RosterAssignment.user_id == user_id,
        )
    )
    row = prev.scalar_one_or_none()
    if row:
        row.slot = slot_norm
    else:
        db.add(
            RosterAssignment(
                scope=rv,
                guild_slug=store_guild,
                rate=safe_rate,
                slot=slot_norm,
                user_id=user_id,
            )
        )
    await db.commit()
    return RedirectResponse(url=dest, status_code=303)


@router.get("/rosters/{slug}")
async def roster_legacy_redirect(slug: str, user: Annotated[User | None, Depends(get_optional_user)]):
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)
    page = get_roster_page(slug)
    if page is None:
        raise HTTPException(status_code=404, detail="Unknown roster")
    return RedirectResponse("/rosters", status_code=302)

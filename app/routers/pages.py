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
from app.roster_data import (
    ALLIANCE_PAGE,
    GUILD_PAGES,
    RATES,
    default_roster_board_path,
    filter_roster_available_players,
    get_roster_page,
    guild_choices_for_roster,
    roster_board_url,
    roster_player_display_name,
    roster_pool_eligible_user,
    user_can_open_guild_board,
)
from app.services.discord_api import fetch_members_with_role

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["pages"])


def _roster_assignment_redirect_url(roster_view: str, rate: int, guild_slug: str | None) -> str:
    if roster_view == "guild" and guild_slug:
        return roster_board_url("guild", rate, guild_slug)
    return roster_board_url("alliance", rate)


async def _load_roster_slot_players(
    db: AsyncSession,
    *,
    roster_view: str,
    guild_slug: str | None,
    rate: int,
) -> tuple[list[User], list[User], dict[int, str]]:
    gstore = (guild_slug or "").strip().lower() if roster_view == "guild" else ""
    res = await db.execute(
        select(RosterAssignment)
        .where(RosterAssignment.scope == roster_view)
        .where(RosterAssignment.guild_slug == gstore)
        .where(RosterAssignment.rate == rate)
    )
    assigns = list(res.scalars().all())
    if not assigns:
        return [], [], {}
    by_slot: dict[str, list[int]] = {"a": [], "b": []}
    uid_to_slot: dict[int, str] = {}
    for a in assigns:
        if a.slot in ("a", "b"):
            by_slot.setdefault(a.slot, []).append(a.user_id)
        uid_to_slot[a.user_id] = a.slot
    uids = list({a.user_id for a in assigns})
    ures = await db.execute(select(User).where(User.id.in_(uids)))
    users_map = {u.id: u for u in ures.scalars().all()}

    def sort_ids(ids: list[int]) -> list[int]:
        return sorted(
            ids,
            key=lambda uid: (
                roster_player_display_name(users_map[uid]).lower(),
                users_map[uid].discord_id,
            ),
        )

    a_players = [users_map[uid] for uid in sort_ids(by_slot.get("a", [])) if uid in users_map]
    b_players = [users_map[uid] for uid in sort_ids(by_slot.get("b", [])) if uid in users_map]
    return a_players, b_players, uid_to_slot


def _template_ctx(settings, **extra) -> dict:
    out = {
        "app_name": settings.app_name,
        "site_background_image": settings.site_background_image or None,
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
    return RedirectResponse(roster_board_url("alliance", 1), status_code=302)


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
    if not user_can_open_guild_board(user, gslug):
        return RedirectResponse("/dashboard?forbidden=roster", status_code=303)
    return RedirectResponse(roster_board_url("guild", 1, gslug), status_code=302)


@router.get("/guild/{slug}", response_class=HTMLResponse)
async def guild_landing_page(
    request: Request,
    slug: str,
    user: Annotated[User | None, Depends(get_optional_user)],
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
            roster_board_url=roster_board_url,
        ),
    )


@router.get("/rosters", response_class=HTMLResponse)
async def rosters_board(
    request: Request,
    user: Annotated[User | None, Depends(get_optional_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    view: str | None = Query(None),
    guild: str | None = Query(None),
    rate: int = Query(1, ge=1, le=6),
):
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)
    view_raw = (view or "").strip()
    if not view_raw:
        return RedirectResponse(default_roster_board_path(user), status_code=302)

    v = view_raw.lower()
    if v not in ("alliance", "guild"):
        return RedirectResponse(default_roster_board_path(user), status_code=302)

    choices = guild_choices_for_roster(user)
    current_guild: str | None = None
    current_guild_name = ALLIANCE_PAGE["name"]

    if v == "guild":
        if not choices:
            return RedirectResponse(roster_board_url("alliance", rate), status_code=302)
        allowed = {c["slug"] for c in choices}
        gslug = (guild or "").strip().lower()
        if gslug not in allowed:
            gslug = choices[0]["slug"]
        if not user_can_open_guild_board(user, gslug):
            return RedirectResponse("/dashboard?forbidden=roster", status_code=303)
        current_guild = gslug
        info = get_guild_landing_page(gslug)
        current_guild_name = info["name"] if info else gslug
    else:
        current_guild = None

    roster_users_result = await db.execute(
        select(User).where(User.home_guild_tag.isnot(None)).where(User.home_guild_tag != "")
    )
    roster_users = roster_users_result.scalars().all()
    available_players = filter_roster_available_players(
        roster_users, view=v, guild_slug=current_guild
    )

    roster_a_players, roster_b_players, assignment_by_user_id = await _load_roster_slot_players(
        db,
        roster_view=v,
        guild_slug=current_guild,
        rate=rate,
    )

    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "rosters.html",
        _template_ctx(
            settings,
            user=user,
            view=v,
            rate=rate,
            current_guild=current_guild,
            current_guild_name=current_guild_name,
            guild_choices=choices,
            rates=RATES,
            roster_board_url=roster_board_url,
            available_players=available_players,
            roster_player_display_name=roster_player_display_name,
            roster_a_players=roster_a_players,
            roster_b_players=roster_b_players,
            assignment_by_user_id=assignment_by_user_id,
            can_manage_rosters=user.can_manage_roster_assignments(),
            tier_display="Tier #",
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
    if page["kind"] == "alliance":
        return RedirectResponse(roster_board_url("alliance", 1), status_code=302)
    gslug = page["slug"]
    if not user_can_open_guild_board(user, gslug):
        return RedirectResponse("/dashboard?forbidden=roster", status_code=303)
    return RedirectResponse(roster_board_url("guild", 1, gslug), status_code=302)

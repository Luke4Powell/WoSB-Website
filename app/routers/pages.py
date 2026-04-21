from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.deps import get_optional_user, require_user_redirect
from app.guild_landing_data import get_guild_landing_page, guild_discord_role_id
from app.ships_catalog import load_catalog
from app.upgrades_catalog import (
    NOT_UNLOCKED_YET_LABEL,
    STRUCTURAL_EXPANSION_LABEL,
    load_upgrades_catalog,
)
from app.consumables_catalog import load_consumables_catalog
from app.models import User
from app.roster_data import (
    ALLIANCE_PAGE,
    GUILD_PAGES,
    RATES,
    default_roster_board_path,
    get_roster_page,
    guild_choices_for_roster,
    roster_board_url,
    user_can_open_guild_board,
)
from app.services.discord_api import fetch_members_with_role

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["pages"])


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
async def tools(request: Request, user: Annotated[User | None, Depends(get_optional_user)]):
    if user is None:
        return RedirectResponse("/auth/login", status_code=302)
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "tools.html",
        _template_ctx(settings, user=user),
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
        ),
    )


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

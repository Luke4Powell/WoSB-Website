from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.services.discord_api import (
    build_authorize_url,
    exchange_code,
    fetch_discord_user,
    fetch_guild_member,
    generate_oauth_state,
    infer_guild_tag_from_roles,
    map_roles_to_flags,
)

router = APIRouter(tags=["auth"])


def _role_id_strings_from_member(member: dict) -> list[str]:
    role_ids = member.get("roles") or []
    if not isinstance(role_ids, list):
        return []
    return [str(r).strip() for r in role_ids if r is not None and str(r).strip()]


def apply_guild_member_roles_to_user(user: User, member: dict, settings: Settings) -> None:
    """Update leadership flags and home_guild_tag from a Discord guild member payload (bot API)."""
    role_id_strs = _role_id_strings_from_member(member)
    is_admiral, is_leader, is_alliance_leader, is_officer, is_member = map_roles_to_flags(
        settings, role_id_strs
    )
    inferred_guild_tag = infer_guild_tag_from_roles(settings, role_id_strs)
    user.is_admiral = is_admiral
    user.is_leader = is_leader
    user.is_alliance_leader = is_alliance_leader
    user.is_officer = is_officer
    user.is_member = is_member
    if inferred_guild_tag:
        user.home_guild_tag = inferred_guild_tag
    elif not (is_admiral or is_leader or is_alliance_leader or is_officer or is_member):
        user.home_guild_tag = None


@router.get("/login")
async def discord_login(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> RedirectResponse:
    state = generate_oauth_state()
    request.session["oauth_state"] = state
    url = build_authorize_url(settings, state)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def discord_callback(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        return RedirectResponse("/?auth_error=discord_denied", status_code=status.HTTP_302_FOUND)
    saved = request.session.pop("oauth_state", None)
    if not state or not saved or state != saved:
        return RedirectResponse("/?auth_error=oauth_state", status_code=status.HTTP_302_FOUND)
    if not code:
        return RedirectResponse("/?auth_error=oauth_code", status_code=status.HTTP_302_FOUND)

    token_payload = await exchange_code(settings, code)
    access_token = token_payload.get("access_token")
    if not access_token or not isinstance(access_token, str):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Discord token response invalid")

    d_user = await fetch_discord_user(access_token)
    discord_id = int(d_user["id"])

    member = await fetch_guild_member(settings, str(discord_id))
    if member is None:
        return RedirectResponse("/?auth_error=not_in_guild", status_code=status.HTTP_302_FOUND)

    username = str(d_user.get("username") or "")
    global_name = d_user.get("global_name")
    if global_name is not None:
        global_name = str(global_name)
    avatar_hash = d_user.get("avatar")
    if avatar_hash is not None:
        avatar_hash = str(avatar_hash)

    row = await db.execute(select(User).where(User.discord_id == discord_id))
    user = row.scalar_one_or_none()
    if user is None:
        user = User(
            discord_id=discord_id,
            username=username,
            global_name=global_name,
            avatar_hash=avatar_hash,
        )
        db.add(user)
        apply_guild_member_roles_to_user(user, member, settings)
    else:
        user.username = username
        user.global_name = global_name
        user.avatar_hash = avatar_hash
        apply_guild_member_roles_to_user(user, member, settings)

    if not user.can_access_member_features():
        await db.commit()
        return RedirectResponse("/?auth_error=missing_member_role", status_code=status.HTTP_302_FOUND)

    await db.commit()

    request.session["discord_id"] = str(discord_id)
    return RedirectResponse("/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)

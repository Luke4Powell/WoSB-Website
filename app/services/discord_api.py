import secrets
from urllib.parse import urlencode

import httpx

from app.config import Settings

DISCORD_API = "https://discord.com/api/v10"
OAUTH_AUTHORIZE = "https://discord.com/oauth2/authorize"
OAUTH_TOKEN = "https://discord.com/api/oauth2/token"


def build_authorize_url(settings: Settings, state: str) -> str:
    if not settings.discord_client_id or not settings.discord_redirect_uri:
        raise RuntimeError("Discord OAuth is not configured (client id / redirect uri).")
    q = urlencode(
        {
            "client_id": settings.discord_client_id,
            "response_type": "code",
            "redirect_uri": settings.discord_redirect_uri,
            "scope": "identify",
            "state": state,
        }
    )
    return f"{OAUTH_AUTHORIZE}?{q}"


def generate_oauth_state() -> str:
    return secrets.token_urlsafe(32)


async def exchange_code(settings: Settings, code: str) -> dict:
    if not settings.discord_client_secret:
        raise RuntimeError("DISCORD_CLIENT_SECRET is not set.")
    data = {
        "client_id": settings.discord_client_id,
        "client_secret": settings.discord_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.discord_redirect_uri,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(OAUTH_TOKEN, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        r.raise_for_status()
        return r.json()


async def fetch_discord_user(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        return r.json()


async def fetch_guild_member(settings: Settings, discord_user_id: str) -> dict | None:
    if not settings.discord_bot_token or not settings.discord_guild_id:
        raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required to verify guild membership.")
    url = f"{DISCORD_API}/guilds/{settings.discord_guild_id}/members/{discord_user_id}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers={"Authorization": f"Bot {settings.discord_bot_token}"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


def map_roles_to_flags(settings: Settings, role_ids: list[str]) -> tuple[bool, bool, bool, bool]:
    ids = {str(r).strip() for r in role_ids if r is not None and str(r).strip()}
    admiral = bool(
        (rid := str(settings.discord_role_admiral_id or "").strip()) and rid in ids
    )
    leader = bool((rid := str(settings.discord_role_leader_id or "").strip()) and rid in ids)
    alliance = bool(
        (rid := str(settings.discord_role_alliance_leader_id or "").strip()) and rid in ids
    )
    officer = bool((rid := str(settings.discord_role_officer_id or "").strip()) and rid in ids)
    return admiral, leader, alliance, officer


async def fetch_members_with_role(
    settings: Settings,
    role_id: str,
    *,
    max_pages: int = 25,
) -> list[dict[str, str | None]]:
    """Return display-ready rows for members who have ``role_id`` (guild-wide scan, paginated).

    Requires ``DISCORD_BOT_TOKEN``, ``DISCORD_GUILD_ID``, and the **Server Members** privileged intent
    on the bot if your server is large. Caps pagination for safety.
    """
    if not settings.discord_bot_token or not settings.discord_guild_id or not role_id:
        return []

    guild_id = settings.discord_guild_id
    headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
    out: list[dict[str, str | None]] = []
    after: str | None = None

    async with httpx.AsyncClient() as client:
        for _ in range(max_pages):
            params: dict[str, str] = {"limit": "1000"}
            if after:
                params["after"] = after
            r = await client.get(
                f"{DISCORD_API}/guilds/{guild_id}/members",
                headers=headers,
                params=params,
                timeout=45.0,
            )
            r.raise_for_status()
            batch = r.json()
            if not isinstance(batch, list) or not batch:
                break
            for m in batch:
                roles = m.get("roles") or []
                if not isinstance(roles, list) or role_id not in roles:
                    continue
                u = m.get("user") or {}
                uid = str(u.get("id") or "")
                avatar = u.get("avatar")
                out.append(
                    {
                        "id": uid,
                        "username": str(u.get("username") or ""),
                        "global_name": u.get("global_name"),
                        "nick": m.get("nick"),
                        "avatar_hash": str(avatar) if avatar else None,
                    }
                )
            if len(batch) < 1000:
                break
            last_user = (batch[-1].get("user") or {}).get("id")
            if not last_user:
                break
            after = str(last_user)

    def sort_key(row: dict[str, str | None]) -> str:
        return (row.get("nick") or row.get("global_name") or row.get("username") or "").lower()

    out.sort(key=sort_key)
    return out


def infer_guild_tag_from_roles(settings: Settings, role_ids: list[str]) -> str | None:
    """First matching guild role wins (TIF, BWC, SVA, LP). Returns a tag stored on `User.home_guild_tag`."""
    ids = {str(r).strip() for r in role_ids if r is not None and str(r).strip()}
    pairs: list[tuple[str, str]] = [
        (str(settings.discord_role_guild_tif_id or "").strip(), "TIF"),
        (str(settings.discord_role_guild_bwc_id or "").strip(), "BWC"),
        (str(settings.discord_role_guild_sva_id or "").strip(), "SVA"),
        (str(settings.discord_role_guild_lp_id or "").strip(), "LP☠"),
    ]
    for rid, tag in pairs:
        if rid and rid in ids:
            return tag
    return None

"""Roster board metadata, access rules, and Discord→guild mapping helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from app.models import User

RATES: tuple[int, ...] = (1, 2, 3, 4, 5, 6)

ALLIANCE_PAGE: dict[str, Any] = {
    "slug": "alliance",
    "tag": "Alliance",
    "name": "Alliance roster",
    "kind": "alliance",
}

GUILD_PAGES: tuple[dict[str, Any], ...] = (
    {
        "slug": "tif",
        "tag": "TIF",
        "name": "The Iron Fleet",
        "kind": "guild",
    },
    {
        "slug": "bwc",
        "tag": "BWC",
        "name": "Blackwolf Chapter",
        "kind": "guild",
    },
    {
        "slug": "sva",
        "tag": "SVA",
        "name": "La Armada Soberana",
        "kind": "guild",
    },
    {
        "slug": "lp",
        "tag": "LP☠",
        "name": "Loose Talk, Live Powder",
        "kind": "guild",
    },
)

ROSTER_PAGES: tuple[dict[str, Any], ...] = (ALLIANCE_PAGE, *GUILD_PAGES)
_GUILDS_BY_SLUG = {g["slug"]: g for g in GUILD_PAGES}


def roster_board_url(view: str, rate: int = 1, guild: str | None = None) -> str:
    q: dict[str, str] = {"view": view, "rate": str(max(1, min(6, rate)))}
    if view == "guild" and guild:
        q["guild"] = guild
    return f"/rosters?{urlencode(q)}"


def get_guild_landing(slug: str) -> dict[str, Any] | None:
    key = (slug or "").strip().lower()
    return _GUILDS_BY_SLUG.get(key)


def get_roster_page(slug: str) -> dict[str, Any] | None:
    key = (slug or "").strip().lower()
    if key == ALLIANCE_PAGE["slug"]:
        return ALLIANCE_PAGE
    return _GUILDS_BY_SLUG.get(key)


def home_tag_to_guild_slug(tag: str | None) -> str | None:
    if not tag:
        return None
    t = tag.strip().upper().replace(" ", "")
    if t.startswith("LP"):
        return "lp"
    mapping = {"TIF": "tif", "BWC": "bwc", "SVA": "sva"}
    return mapping.get(t)


def guild_choices_for_roster(user: User) -> list[dict[str, Any]]:
    """Guilds this user may pick in the roster dropdown."""
    if user.is_admiral or user.is_leader:
        return list(GUILD_PAGES)
    slug = home_tag_to_guild_slug(user.home_guild_tag)
    if not slug:
        return []
    g = _GUILDS_BY_SLUG.get(slug)
    return [g] if g else []


def default_roster_board_path(user: User) -> str:
    """Where to send a member opening /rosters with no query string."""
    choices = guild_choices_for_roster(user)
    if choices:
        return roster_board_url(view="guild", guild=choices[0]["slug"], rate=1)
    return roster_board_url(view="alliance", rate=1)


def user_can_open_guild_board(user: User, guild_slug: str) -> bool:
    if user.is_admiral or user.is_leader:
        return True
    home_slug = home_tag_to_guild_slug(user.home_guild_tag)
    return home_slug is not None and home_slug == (guild_slug or "").strip().lower()

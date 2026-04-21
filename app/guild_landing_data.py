"""Copy + optional art paths for Spanish Faction guild landing pages (guild pages, public HTML)."""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.roster_data import get_guild_landing

# Optional hero art: add files under /static/images/guilds/ and set the path here (must start with /static/).
LANDING_COPY: dict[str, dict[str, Any]] = {
    "tif": {
        "hero_image": "/static/images/guilds/tif-hero.png",
        "slogan": (
            "Welcome to TIF. The oldest and most dedicated Spanish guild. Together with our brother guilds, "
            "we hold the line and keep Spain alive. When everyone else falters, we stand strong."
        ),
        "intro": (
            "Use this space for port nights, screening rosters, and fleet announcements—keep it current for the crew."
        ),
    },
    "bwc": {
        "hero_image": "/static/images/guilds/bwc-hero.png",
        "slogan": "Blackwolf runs silent until the bell rings.",
        "intro": "Blackwolf Chapter guild page — orders, night actions, and fleet posture live here.",
    },
    "sva": {
        "hero_image": "/static/images/guilds/sva-hero.png",
        "slogan": "Soberana steel, Caribbean resolve.",
        "intro": "La Armada Soberana — doctrine, port nights, and screening rosters start on this deck.",
    },
    "lp": {
        "hero_image": "/static/images/guilds/lp-hero.png",
        "slogan": "Loose talk, live powder.",
        "intro": "LP☠ — quick orders, bold screening, and powder when it counts. Personalize this block anytime.",
    },
}


def guild_discord_role_id(settings: Settings, slug: str) -> str:
    key = (slug or "").strip().lower()
    mapping = {
        "tif": settings.discord_role_guild_tif_id,
        "bwc": settings.discord_role_guild_bwc_id,
        "sva": settings.discord_role_guild_sva_id,
        "lp": settings.discord_role_guild_lp_id,
    }
    return (mapping.get(key) or "").strip()


def get_guild_landing_page(slug: str) -> dict[str, Any] | None:
    base = get_guild_landing(slug)
    if base is None:
        return None
    key = base["slug"]
    extra = LANDING_COPY.get(key, {})
    return {**base, **extra}

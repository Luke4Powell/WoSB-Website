"""Port battle roster sessions: ship mix, ready pool, lineup, ally caps."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import PortBattleLineupSlot, PortBattleReady, PortBattleSession, User
from app.port_battle.logic import lookup_port
from app.roster_data import home_tag_to_guild_slug, roster_player_display_name
from app.ships_catalog import ship_by_id

ALLY_CAP_ABSOLUTE = 10


def parse_pvp_per_side(pvp_size: str) -> int:
    s = (pvp_size or "").strip().lower().replace(" ", "")
    if "v" in s:
        left, _, _ = s.partition("v")
        if left.isdigit():
            return max(1, min(64, int(left)))
    digits = "".join(c for c in s if c.isdigit())
    if digits:
        return max(1, min(64, int(digits)))
    return 20


def max_allies_for_primaries(primary_in_lineup: int) -> int:
    return min(ALLY_CAP_ABSOLUTE, max(0, primary_in_lineup))


def normalize_ship_mix(raw: list[dict[str, Any]], *, valid_ship_ids: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("ship_id", "")).strip()
        try:
            qty = int(row.get("qty", 0))
        except (TypeError, ValueError):
            qty = 0
        if not sid or sid not in valid_ship_ids or qty <= 0:
            continue
        qty = min(qty, 64)
        out.append({"ship_id": sid, "qty": qty})
    return out


def validate_mix_total(mix: list[dict[str, Any]], per_side: int) -> str | None:
    if not mix:
        return None
    total = sum(int(x["qty"]) for x in mix)
    if total != per_side:
        return f"Ship counts must sum to {per_side} (one side); currently {total}."
    return None


def user_slug_matches_primary(user: User, primary_slug: str) -> bool:
    slug = home_tag_to_guild_slug(user.home_guild_tag)
    return slug is not None and slug == (primary_slug or "").strip().lower()


def lineup_primary_ally_counts(
    users_by_id: dict[int, User], *, primary_slug: str, assigned_user_ids: list[int | None]
) -> tuple[int, int]:
    primary = 0
    ally = 0
    for uid in assigned_user_ids:
        if uid is None:
            continue
        u = users_by_id.get(uid)
        if u is None:
            continue
        if user_slug_matches_primary(u, primary_slug):
            primary += 1
        else:
            ally += 1
    return primary, ally


def lineup_violates_ally_cap(
    *,
    users_by_id: dict[int, User],
    primary_slug: str,
    assigned_user_ids: list[int | None],
) -> str | None:
    """Return error message if primary/ally counts break the cap; None if OK."""
    primaries = 0
    allies = 0
    for uid in assigned_user_ids:
        if uid is None:
            continue
        u = users_by_id.get(uid)
        if u is None:
            return "Unknown user on lineup."
        if user_slug_matches_primary(u, primary_slug):
            primaries += 1
        else:
            allies += 1
    cap = max_allies_for_primaries(primaries)
    if allies > cap:
        return (
            f"Ally seats are capped at {cap} "
            f"(min of {ALLY_CAP_ABSOLUTE} and primary-guild count on the roster)."
        )
    return None


async def load_session_bundle(
    db: AsyncSession, session_id: int
) -> tuple[PortBattleSession | None, list[PortBattleReady], list[PortBattleLineupSlot]]:
    sess = await db.get(PortBattleSession, session_id)
    if sess is None:
        return None, [], []
    ready_r = await db.execute(select(PortBattleReady).where(PortBattleReady.session_id == session_id))
    ready_rows = list(ready_r.scalars().all())
    line_r = await db.execute(
        select(PortBattleLineupSlot)
        .where(PortBattleLineupSlot.session_id == session_id)
        .order_by(PortBattleLineupSlot.slot_index.asc())
    )
    slots = list(line_r.scalars().all())
    return sess, ready_rows, slots


async def session_mix_list(sess: PortBattleSession) -> list[dict[str, Any]]:
    try:
        data = json.loads(sess.ship_mix_json or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def mix_rows_display(mix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in mix:
        sid = str(row.get("ship_id", ""))
        ship = ship_by_id(sid)
        out.append(
            {
                "ship_id": sid,
                "qty": int(row.get("qty", 0)),
                "name": (ship or {}).get("name") or sid,
            }
        )
    return out


def port_row_for_name(port_name: str) -> dict[str, Any] | None:
    return lookup_port(port_name)


async def build_session_json(
    db: AsyncSession,
    sess: PortBattleSession,
    *,
    ready_rows: list[PortBattleReady],
    slots: list[PortBattleLineupSlot],
    voice_by_discord_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    mix = await session_mix_list(sess)
    uids = list({r.user_id for r in ready_rows} | {s.user_id for s in slots if s.user_id is not None})
    users_map: dict[int, User] = {}
    if uids:
        ur = await db.execute(select(User).where(User.id.in_(uids)))
        users_map = {u.id: u for u in ur.scalars().all()}

    assigned = [s.user_id for s in slots]
    prim, ally = lineup_primary_ally_counts(
        users_map, primary_slug=sess.primary_guild_slug, assigned_user_ids=assigned
    )
    ally_cap = max_allies_for_primaries(prim)

    def _ready_sort_key(r: PortBattleReady) -> str:
        u = users_map.get(r.user_id)
        return roster_player_display_name(u).lower() if u else str(r.user_id)

    ready_by_user_id: dict[int, dict[str, Any]] = {}
    readied = []
    for r in sorted(ready_rows, key=_ready_sort_key):
        u = users_map.get(r.user_id)
        ship = ship_by_id(r.ship_id)
        did = str(u.discord_id) if u else ""
        vs = (voice_by_discord_id or {}).get(did) if did else None
        row = {
            "user_id": r.user_id,
            "display": roster_player_display_name(u) if u else str(r.user_id),
            "guild_tag": u.home_guild_tag if u else None,
            "guild_slug": home_tag_to_guild_slug(u.home_guild_tag) if u else None,
            "instance_id": r.instance_id,
            "ship_id": r.ship_id,
            "ship_name": (ship or {}).get("name") or r.ship_id,
            "in_voice": bool(vs and vs.get("channel_id")),
            "voice_channel_id": vs.get("channel_id") if vs else None,
        }
        readied.append(row)
        ready_by_user_id[r.user_id] = row

    lineup = []
    for s in slots:
        u = users_map.get(s.user_id) if s.user_id else None
        did = str(u.discord_id) if u else ""
        vs = (voice_by_discord_id or {}).get(did) if did else None
        lineup.append(
            {
                "slot_index": s.slot_index,
                "user_id": s.user_id,
                "display": roster_player_display_name(u) if u else None,
                "guild_tag": u.home_guild_tag if u else None,
                "guild_slug": home_tag_to_guild_slug(u.home_guild_tag) if u else None,
                "in_voice": bool(vs and vs.get("channel_id")),
                "ready": bool(s.user_id and s.user_id in ready_by_user_id),
                "ship_id": ready_by_user_id.get(s.user_id or 0, {}).get("ship_id"),
                "ship_name": ready_by_user_id.get(s.user_id or 0, {}).get("ship_name"),
            }
        )

    return {
        "id": sess.id,
        "scope": sess.scope,
        "guild_slug": sess.guild_slug or None,
        "primary_guild_slug": sess.primary_guild_slug,
        "port_name": sess.port_name,
        "rate_text": sess.rate_text,
        "rate_num": sess.rate_num,
        "per_side": sess.per_side,
        "pvp_label": sess.pvp_label,
        "ship_mix": mix_rows_display(mix),
        "status": sess.status,
        "created_by_user_id": sess.created_by_user_id,
        "readied": readied,
        "lineup": lineup,
        "lineup_counts": {"primary": prim, "ally": ally, "ally_cap": ally_cap},
    }


_SLUG_RE = re.compile(r"^[a-z0-9]{1,32}$")


def normalize_primary_slug(v: str) -> str | None:
    s = (v or "").strip().lower()
    if not s or not _SLUG_RE.match(s):
        return None
    return s

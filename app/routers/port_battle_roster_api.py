"""JSON API for port battle roster sessions (create, ready-up, lineup, lock)."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.deps import require_user
from app.models import PortBattleLineupSlot, PortBattleReady, PortBattleSession, User
from app.roster_data import (
    GUILD_PAGES,
    roster_player_display_name,
    roster_pool_eligible_user,
    user_can_open_guild_board,
)
from app.schemas.fleet import fleet_from_json
from app.services.discord_api import fetch_all_guild_members, infer_guild_tag_from_roles
from app.services.discord_voice_tracker import get_voice_snapshot, get_voice_tracker_stats
from app.services.port_battle_roster import (
    ALLY_CAP_ABSOLUTE,
    build_session_json,
    lineup_violates_ally_cap,
    load_session_bundle,
    normalize_primary_slug,
    normalize_ship_mix,
    parse_pvp_per_side,
    port_row_for_name,
    validate_mix_total,
)
from app.ships_catalog import catalog_ship_ids

router = APIRouter(prefix="/api/port-battles", tags=["port-battle-roster"])

_ALLOWED_PRIMARY = {str(g["slug"]).lower() for g in GUILD_PAGES}


def _store_guild_slug(scope: str, guild_slug: str | None) -> str:
    if scope == "guild":
        return (guild_slug or "").strip().lower()
    return ""


def _session_access(user: User, sess: PortBattleSession) -> bool:
    if sess.scope == "guild":
        return roster_pool_eligible_user(user, view="guild", guild_slug=sess.guild_slug)
    return roster_pool_eligible_user(user, view="alliance", guild_slug=None)


class ShipMixRow(BaseModel):
    ship_id: str = Field(default="", max_length=128)
    qty: int = Field(default=0, ge=0, le=64)


class CreateSessionBody(BaseModel):
    port_name: str = Field(default="", max_length=200)
    primary_guild_slug: str = Field(default="", max_length=32)
    ship_mix: list[ShipMixRow] = Field(default_factory=list)


class ReadyBody(BaseModel):
    instance_id: str = Field(default="", max_length=128)


class LineupPatchBody(BaseModel):
    slot_index: int = Field(ge=0, le=127)
    user_id: int | None = None


class AssignReadyBody(BaseModel):
    user_id: int


def _ordered_slot_user_ids(slots: list[PortBattleLineupSlot]) -> list[int | None]:
    if not slots:
        return []
    m = {s.slot_index: s.user_id for s in slots}
    mx = max(m.keys())
    return [m.get(i) for i in range(mx + 1)]


@router.get("/meta/port")
async def meta_port(
    user: Annotated[User, Depends(require_user)],
    name: str = Query("", alias="name"),
):
    _ = user
    prow = port_row_for_name(name)
    if not prow:
        raise HTTPException(status_code=404, detail="Unknown port")
    per_side = parse_pvp_per_side(str(prow.get("pvp_size", "")))
    return {
        "port_name": str(prow.get("name", "")),
        "rate_text": str(prow.get("rate_text", "")),
        "rate_num": int(prow.get("rate_num", 1) or 1),
        "pvp_label": str(prow.get("pvp_size", "")),
        "per_side": per_side,
    }


@router.get("")
async def list_sessions(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    view: str = Query("alliance"),
    guild: str | None = Query(None),
):
    v = (view or "").strip().lower()
    if v not in ("alliance", "guild"):
        raise HTTPException(status_code=400, detail="view must be alliance or guild")
    gslug = (guild or "").strip().lower() if v == "guild" else ""
    if v == "guild" and not user_can_open_guild_board(user, gslug):
        raise HTTPException(status_code=403, detail="Guild roster not available")

    store = _store_guild_slug(v, gslug)
    r = await db.execute(
        select(PortBattleSession)
        .where(PortBattleSession.scope == v, PortBattleSession.guild_slug == store)
        .order_by(PortBattleSession.created_at.desc())
        .limit(50)
    )
    rows = list(r.scalars().all())
    return {
        "sessions": [
            {
                "id": s.id,
                "port_name": s.port_name,
                "rate_text": s.rate_text,
                "per_side": s.per_side,
                "primary_guild_slug": s.primary_guild_slug,
                "status": s.status,
                "pvp_label": s.pvp_label,
            }
            for s in rows
        ],
    }


@router.post("")
async def create_session(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: CreateSessionBody,
    view: str = Query("alliance"),
    guild: str | None = Query(None),
):
    if not user.can_manage_roster_assignments():
        raise HTTPException(status_code=403, detail="Not allowed to create battles")
    v = (view or "").strip().lower()
    if v not in ("alliance", "guild"):
        raise HTTPException(status_code=400, detail="view must be alliance or guild")
    gslug = (guild or "").strip().lower() if v == "guild" else ""
    if v == "guild" and not user_can_open_guild_board(user, gslug):
        raise HTTPException(status_code=403, detail="Guild roster not available")

    primary = normalize_primary_slug(body.primary_guild_slug)
    if not primary or primary not in _ALLOWED_PRIMARY:
        raise HTTPException(status_code=400, detail="primary_guild_slug must be a guild slug (tif, bwc, sva, lp)")

    port_name = (body.port_name or "").strip()
    prow = port_row_for_name(port_name)
    if not prow:
        raise HTTPException(status_code=400, detail="Unknown port name")

    per_side = parse_pvp_per_side(str(prow.get("pvp_size", "")))
    valid = catalog_ship_ids()
    mix = normalize_ship_mix([r.model_dump() for r in body.ship_mix], valid_ship_ids=valid)
    err = validate_mix_total(mix, per_side)
    if err:
        raise HTTPException(status_code=400, detail=err)

    store = _store_guild_slug(v, gslug)
    sess = PortBattleSession(
        scope=v,
        guild_slug=store,
        primary_guild_slug=primary,
        port_name=str(prow.get("name", port_name))[:200],
        rate_text=str(prow.get("rate_text", ""))[:64],
        rate_num=int(prow.get("rate_num", 1) or 1),
        per_side=per_side,
        pvp_label=str(prow.get("pvp_size", ""))[:32],
        ship_mix_json=json.dumps(mix),
        status="open",
        created_by_user_id=user.id,
    )
    db.add(sess)
    await db.flush()
    for i in range(per_side):
        db.add(PortBattleLineupSlot(session_id=sess.id, slot_index=i, user_id=None))
    await db.commit()
    await db.refresh(sess)
    _, ready_rows, slots = await load_session_bundle(db, sess.id)
    return await build_session_json(db, sess, ready_rows=ready_rows, slots=slots)


@router.get("/{session_id:int}")
async def get_session(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_id: int,
    include_voice: bool = Query(True),
):
    sess, ready_rows, slots = await load_session_bundle(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not _session_access(user, sess):
        raise HTTPException(status_code=403, detail="Not allowed")

    voice_map: dict[str, dict[str, str | None]] | None = None
    all_users_res = await db.execute(select(User))
    all_users = list(all_users_res.scalars().all())
    local_by_discord_id = {str(u.discord_id): u for u in all_users if u.discord_id}

    guild_members: list[dict[str, str | list[str] | None]] = []
    if include_voice:
        settings = get_settings()
        guild_members = await fetch_all_guild_members(settings)
        live_voice = await get_voice_snapshot()
        voice_map = {uid: {"channel_id": ch} for uid, ch in live_voice.items() if ch}

    payload = await build_session_json(db, sess, ready_rows=ready_rows, slots=slots, voice_by_discord_id=voice_map)
    if include_voice and voice_map is not None:
        voice_rows = []
        for member in guild_members:
            did = str(member.get("id") or "").strip()
            if not did:
                continue
            vs = voice_map.get(did) or {}
            ch = vs.get("channel_id")
            if not ch:
                continue
            u = local_by_discord_id.get(did)
            display = str(member.get("nick") or member.get("global_name") or member.get("username") or did)
            guild_tag = u.home_guild_tag if u else infer_guild_tag_from_roles(settings, list(member.get("roles") or []))
            voice_rows.append(
                {
                    "user_id": u.id if u else None,
                    "display": display,
                    "guild_tag": guild_tag,
                    "discord_id": did,
                    "in_voice": bool(ch),
                    "voice_channel_id": ch,
                }
            )
        voice_rows.sort(key=lambda r: (not r["in_voice"], r["display"].lower()))
        payload["voice_pool"] = voice_rows
        tracker_stats = await get_voice_tracker_stats()
        payload["voice_debug"] = {
            "scanned_members": len(guild_members),
            "connected_members": len(voice_rows),
            "tracker_connected_users": int(tracker_stats.get("connected_count") or 0),
            "tracker_running": bool(tracker_stats.get("running")),
            "tracker_last_error": str(tracker_stats.get("last_error") or ""),
            "warning": (
                "No guild members returned by Discord. Check DISCORD_GUILD_ID, bot token, and Server Members intent."
                if len(guild_members) == 0
                else
                "Voice tracker connected to Discord but has no current voice users. Confirm users are in normal voice channels and bot has Guild Voice States intent."
                if len(guild_members) > 0 and len(voice_rows) == 0 and bool(tracker_stats.get("running"))
                else
                "Voice tracker is not running. Check bot token/guild and server logs."
                if not bool(tracker_stats.get("running"))
                else ""
            ),
        }
    return payload


@router.delete("/{session_id:int}")
async def delete_session(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_id: int,
):
    if not user.can_manage_roster_assignments():
        raise HTTPException(status_code=403, detail="Not allowed")
    sess = await db.get(PortBattleSession, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not _session_access(user, sess):
        raise HTTPException(status_code=403, detail="Not allowed")
    if sess.status == "locked":
        raise HTTPException(status_code=400, detail="Unlock not supported; session is locked")
    await db.execute(delete(PortBattleLineupSlot).where(PortBattleLineupSlot.session_id == session_id))
    await db.execute(delete(PortBattleReady).where(PortBattleReady.session_id == session_id))
    await db.execute(delete(PortBattleSession).where(PortBattleSession.id == session_id))
    await db.commit()
    return {"ok": True}


@router.post("/{session_id:int}/ready")
async def post_ready(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_id: int,
    body: ReadyBody,
):
    sess, ready_rows, slots = await load_session_bundle(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not _session_access(user, sess):
        raise HTTPException(status_code=403, detail="Not allowed")
    if sess.status != "open":
        raise HTTPException(status_code=400, detail="Session is not accepting ready-ups")

    iid = (body.instance_id or "").strip()
    if not iid:
        raise HTTPException(status_code=400, detail="instance_id required")

    fleet = fleet_from_json(user.ships_json)
    ship_rec = next((s for s in fleet.ships if s.instance_id == iid), None)
    if ship_rec is None:
        raise HTTPException(status_code=400, detail="That ship is not in your fleet")

    existing = await db.execute(
        select(PortBattleReady).where(
            PortBattleReady.session_id == session_id, PortBattleReady.user_id == user.id
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        row.instance_id = iid
        row.ship_id = ship_rec.ship_id
    else:
        db.add(
            PortBattleReady(
                session_id=session_id,
                user_id=user.id,
                instance_id=iid,
                ship_id=ship_rec.ship_id,
            )
        )
    await db.commit()
    sess2, ready2, slots2 = await load_session_bundle(db, session_id)
    assert sess2 is not None
    return await build_session_json(db, sess2, ready_rows=ready2, slots=slots2)


@router.delete("/{session_id:int}/ready")
async def delete_ready(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_id: int,
):
    sess = await db.get(PortBattleSession, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not _session_access(user, sess):
        raise HTTPException(status_code=403, detail="Not allowed")
    if sess.status != "open":
        raise HTTPException(status_code=400, detail="Session is locked")

    await db.execute(
        delete(PortBattleReady).where(
            PortBattleReady.session_id == session_id, PortBattleReady.user_id == user.id
        )
    )
    slots_r = await db.execute(
        select(PortBattleLineupSlot).where(
            PortBattleLineupSlot.session_id == session_id, PortBattleLineupSlot.user_id == user.id
        )
    )
    for s in slots_r.scalars().all():
        s.user_id = None
    await db.commit()
    sess2, ready2, slots2 = await load_session_bundle(db, session_id)
    assert sess2 is not None
    return await build_session_json(db, sess2, ready_rows=ready2, slots=slots2)


@router.patch("/{session_id:int}/lineup")
async def patch_lineup(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_id: int,
    body: LineupPatchBody,
):
    if not user.can_manage_roster_assignments():
        raise HTTPException(status_code=403, detail="Not allowed")
    sess, ready_rows, slots = await load_session_bundle(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not _session_access(user, sess):
        raise HTTPException(status_code=403, detail="Not allowed")
    if sess.status != "open":
        raise HTTPException(status_code=400, detail="Session is locked")

    slot_row = next((s for s in slots if s.slot_index == body.slot_index), None)
    if slot_row is None:
        raise HTTPException(status_code=400, detail="Invalid slot_index")

    new_uid = body.user_id

    if new_uid is not None:
        ready_uids = {r.user_id for r in ready_rows}
        if new_uid not in ready_uids:
            raise HTTPException(status_code=400, detail="Player must be in the readied pool first")
        for s in slots:
            if s.slot_index != body.slot_index and s.user_id == new_uid:
                raise HTTPException(status_code=400, detail="Player is already assigned to another slot")

    trial = _ordered_slot_user_ids(slots)
    if body.slot_index >= len(trial):
        raise HTTPException(status_code=400, detail="Invalid slot_index")
    trial[body.slot_index] = new_uid

    need_ids = {uid for uid in trial if uid is not None}
    if need_ids:
        ur = await db.execute(select(User).where(User.id.in_(need_ids)))
        users_map = {u.id: u for u in ur.scalars().all()}
    else:
        users_map = {}

    err = lineup_violates_ally_cap(
        users_by_id=users_map,
        primary_slug=sess.primary_guild_slug,
        assigned_user_ids=trial,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)

    slot_row.user_id = new_uid
    await db.commit()

    sess2, ready2, slots2 = await load_session_bundle(db, session_id)
    assert sess2 is not None
    return await build_session_json(db, sess2, ready_rows=ready2, slots=slots2)


@router.post("/{session_id:int}/lineup/assign-ready")
async def assign_to_next_open_slot(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_id: int,
    body: AssignReadyBody,
):
    if not user.can_manage_roster_assignments():
        raise HTTPException(status_code=403, detail="Not allowed")
    sess, ready_rows, slots = await load_session_bundle(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not _session_access(user, sess):
        raise HTTPException(status_code=403, detail="Not allowed")
    if sess.status != "open":
        raise HTTPException(status_code=400, detail="Session is locked")

    user_id = int(body.user_id)
    if any(s.user_id == user_id for s in slots):
        raise HTTPException(status_code=400, detail="Player is already on the battle roster")

    open_slot = next((s for s in slots if s.user_id is None), None)
    if open_slot is None:
        raise HTTPException(status_code=400, detail="No open slot available")
    open_slot.user_id = user_id

    trial = _ordered_slot_user_ids(slots)
    need_ids = {uid for uid in trial if uid is not None}
    users_map: dict[int, User] = {}
    if need_ids:
        ur = await db.execute(select(User).where(User.id.in_(need_ids)))
        users_map = {u.id: u for u in ur.scalars().all()}
    err = lineup_violates_ally_cap(
        users_by_id=users_map,
        primary_slug=sess.primary_guild_slug,
        assigned_user_ids=trial,
    )
    if err:
        open_slot.user_id = None
        raise HTTPException(status_code=400, detail=err)

    await db.commit()
    sess2, ready2, slots2 = await load_session_bundle(db, session_id)
    assert sess2 is not None
    return await build_session_json(db, sess2, ready_rows=ready2, slots=slots2)


@router.delete("/{session_id:int}/lineup/user/{user_id:int}")
async def remove_user_from_lineup(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_id: int,
    user_id: int,
):
    if not user.can_manage_roster_assignments():
        raise HTTPException(status_code=403, detail="Not allowed")
    sess, ready_rows, slots = await load_session_bundle(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not _session_access(user, sess):
        raise HTTPException(status_code=403, detail="Not allowed")
    if sess.status != "open":
        raise HTTPException(status_code=400, detail="Session is locked")

    changed = False
    for s in slots:
        if s.user_id == user_id:
            s.user_id = None
            changed = True
            break
    if not changed:
        raise HTTPException(status_code=404, detail="Player is not on the battle roster")

    await db.commit()
    sess2, ready2, slots2 = await load_session_bundle(db, session_id)
    assert sess2 is not None
    return await build_session_json(db, sess2, ready_rows=ready2, slots=slots2)


@router.post("/{session_id:int}/lock")
async def lock_session(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    session_id: int,
):
    if not user.can_manage_roster_assignments():
        raise HTTPException(status_code=403, detail="Not allowed")
    sess = await db.get(PortBattleSession, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not _session_access(user, sess):
        raise HTTPException(status_code=403, detail="Not allowed")
    sess.status = "locked"
    await db.commit()
    sess2, ready2, slots2 = await load_session_bundle(db, session_id)
    assert sess2 is not None
    return await build_session_json(db, sess2, ready_rows=ready2, slots=slots2)


@router.get("/meta/ally-rule")
async def ally_rule_hint():
    return {
        "ally_cap_absolute": ALLY_CAP_ABSOLUTE,
        "rule": (
            f"Ally seats on the lineup cannot exceed min({ALLY_CAP_ABSOLUTE}, primary-guild count on the lineup)."
        ),
    }

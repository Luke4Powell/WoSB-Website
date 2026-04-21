from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import require_user
from app.models import User
from app.schemas.fleet import FleetPayload, fleet_from_json
from app.ships_catalog import catalog_ship_ids
from app.upgrades_catalog import (
    NOT_UNLOCKED_YET_LABEL,
    STRUCTURAL_EXPANSION_LABEL,
    all_upgrade_labels,
)
from app.consumables_catalog import all_consumable_labels

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/ships")
async def get_my_ships(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    r = await db.execute(select(User).where(User.id == user.id))
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    fleet = fleet_from_json(row.ships_json)
    return fleet.model_dump()


@router.put("/ships")
async def put_my_ships(
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: FleetPayload,
) -> dict:
    valid = catalog_ship_ids()
    if not valid:
        raise HTTPException(
            status_code=503,
            detail="Ship catalog is empty. Add ships to app/data/ships_catalog.json on the server.",
        )
    upgrade_allow = all_upgrade_labels()
    consumable_allow = all_consumable_labels()
    for sh in body.ships:
        if sh.ship_id not in valid:
            raise HTTPException(status_code=400, detail=f"Unknown ship_id: {sh.ship_id}")
        for i in range(4):
            if not sh.upgrades[i].strip():
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Upgrade slots 1–4 need a selection for each row (use "
                        f"{NOT_UNLOCKED_YET_LABEL!r} for slots 2–4 that are not unlocked in-game yet) "
                        f"(ship row {sh.instance_id})."
                    ),
                )
        if sh.upgrades[0].strip() == NOT_UNLOCKED_YET_LABEL:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Upgrade slot 1 must be a real upgrade, not {NOT_UNLOCKED_YET_LABEL!r} "
                    f"(ship row {sh.instance_id})."
                ),
            )
        has_structural = any(u.strip() == STRUCTURAL_EXPANSION_LABEL for u in sh.upgrades)
        if not has_structural:
            for i in (5, 6):
                if sh.upgrades[i].strip():
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Upgrade slots 6–7 are only available when "
                            f"{STRUCTURAL_EXPANSION_LABEL!r} is selected on that ship "
                            f"(row {sh.instance_id})."
                        ),
                    )
        if upgrade_allow:
            for i, u in enumerate(sh.upgrades):
                t = u.strip()
                if t and t not in upgrade_allow:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Upgrade slot {i + 1} must be a listed upgrade: {t!r}",
                    )
        if consumable_allow:
            for j, c in enumerate(sh.consumables):
                t = c.strip()
                if t and t not in consumable_allow:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Consumable slot {j + 1} must be a listed item: {t!r}",
                    )
    r = await db.execute(select(User).where(User.id == user.id))
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    row.ships_json = body.model_dump_json()
    await db.commit()
    return {"ok": True}

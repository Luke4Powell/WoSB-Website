"""Validated JSON shape for `User.ships_json` (Discord players' fleet loadouts)."""

from __future__ import annotations

import json
import secrets
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ships_catalog import catalog_name_index, catalog_ship_ids

MAX_SHIPS = 40
MAX_SLOT_LEN = 160
# Base build uses 5; Structural Expansion allows 2 more (stored as 7 strings).
UPGRADE_SLOTS_MAX = 7
CONSUMABLE_SLOTS = 3


def _clean_str(s: Any, max_len: int = MAX_SLOT_LEN) -> str:
    if s is None:
        return ""
    t = str(s).strip()
    if len(t) > max_len:
        t = t[:max_len]
    return t


def _pad_list(v: Any, length: int) -> list[str]:
    if not isinstance(v, list):
        v = []
    out = [_clean_str(x) for x in v][:length]
    while len(out) < length:
        out.append("")
    return out[:length]


class ShipRecord(BaseModel):
    """One row in the fleet. `instance_id` is unique per row; `ship_id` references the catalog."""

    model_config = ConfigDict(extra="ignore")

    instance_id: str = Field(default="", max_length=128)
    ship_id: str = Field(default="", max_length=128)
    upgrades: list[str] = Field(default_factory=list)
    consumables: list[str] = Field(default_factory=list)

    @field_validator("instance_id", "ship_id", mode="before")
    @classmethod
    def strip_ids(cls, v: Any) -> str:
        return _clean_str(v, 128)

    @field_validator("upgrades", mode="before")
    @classmethod
    def pad_upgrades(cls, v: Any) -> list[str]:
        return _pad_list(v, UPGRADE_SLOTS_MAX)

    @field_validator("consumables", mode="before")
    @classmethod
    def pad_consumables(cls, v: Any) -> list[str]:
        return _pad_list(v, CONSUMABLE_SLOTS)

    @model_validator(mode="after")
    def ensure_instance_id(self) -> ShipRecord:
        if self.instance_id.strip():
            return self
        return self.model_copy(
            update={"instance_id": f"{self.ship_id}-{secrets.token_hex(4)}" if self.ship_id else secrets.token_hex(8)}
        )


class FleetPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = Field(default=1, ge=1, le=99)
    ships: list[ShipRecord] = Field(default_factory=list)

    @field_validator("ships", mode="after")
    @classmethod
    def cap_fleet(cls, ships: list[ShipRecord]) -> list[ShipRecord]:
        return ships[:MAX_SHIPS]


def _normalize_fleet_dict(data: dict) -> dict:
    valid = catalog_ship_ids()
    name_map = catalog_name_index()
    ships_in = data.get("ships")
    if not isinstance(ships_in, list):
        return {"version": int(data.get("version", 1) or 1), "ships": []}
    migrated: list[dict] = []
    for i, item in enumerate(ships_in):
        if not isinstance(item, dict):
            continue
        ship_id = _clean_str(item.get("ship_id", ""), 128)
        instance_id = _clean_str(item.get("instance_id", ""), 128)
        if not ship_id:
            cand = _clean_str(item.get("id", ""), 128)
            if cand in valid:
                ship_id = cand
        if not ship_id:
            legacy_name = _clean_str(item.get("name", ""), 200)
            if legacy_name:
                ship_id = name_map.get(legacy_name.casefold(), "")
        if not valid or ship_id not in valid:
            continue
        if not instance_id:
            legacy_row = _clean_str(item.get("id", ""), 128)
            if legacy_row and legacy_row not in valid:
                instance_id = legacy_row
            else:
                instance_id = f"{ship_id}:{i}"
        migrated.append(
            {
                "instance_id": instance_id,
                "ship_id": ship_id,
                "upgrades": item.get("upgrades"),
                "consumables": item.get("consumables"),
            }
        )
    return {"version": int(data.get("version", 1) or 1), "ships": migrated}


def fleet_from_json(raw: str | None) -> FleetPayload:
    if not raw or not str(raw).strip():
        return FleetPayload(version=1, ships=[])
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return FleetPayload(version=1, ships=[])
    if not isinstance(data, dict):
        return FleetPayload(version=1, ships=[])
    try:
        normalized = _normalize_fleet_dict(data)
        return FleetPayload.model_validate(normalized)
    except Exception:
        return FleetPayload(version=1, ships=[])

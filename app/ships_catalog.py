"""Game ship list for loadouts (`app/data/ships_catalog.json`). Replace `ships` with the full roster."""

from __future__ import annotations

import json
from pathlib import Path

_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "ships_catalog.json"


def load_catalog() -> dict:
    """Return `{ \"ships\": [ { id, name, rate, class }, ... ] }`."""
    if not _CATALOG_PATH.is_file():
        return {"ships": []}
    try:
        data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"ships": []}
    ships = data.get("ships") if isinstance(data, dict) else None
    if not isinstance(ships, list):
        return {"ships": []}
    out = []
    for item in ships:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        if not sid or not name:
            continue
        out.append(
            {
                "id": sid[:128],
                "name": name[:200],
                "rate": str(item.get("rate", "")).strip()[:120],
                "class": str(item.get("class", "")).strip()[:120],
            }
        )
    return {"ships": out}


def catalog_ship_ids() -> set[str]:
    return {s["id"] for s in load_catalog()["ships"]}


def ship_by_id(ship_id: str) -> dict | None:
    for s in load_catalog()["ships"]:
        if s["id"] == ship_id:
            return s
    return None


def catalog_name_index() -> dict[str, str]:
    """lower(name) -> ship id"""
    m: dict[str, str] = {}
    for s in load_catalog()["ships"]:
        key = s["name"].strip().casefold()
        if key:
            m.setdefault(key, s["id"])
    return m

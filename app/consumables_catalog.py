"""Consumable pick lists for fleet loadouts (`app/data/consumables_catalog.json`)."""

from __future__ import annotations

import json
from pathlib import Path

_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "consumables_catalog.json"


def load_consumables_catalog() -> dict:
    """Return `{ \"groups\": [ { id, label, options: [...] }, ... ] }`."""
    if not _CATALOG_PATH.is_file():
        return {"groups": []}
    try:
        data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"groups": []}
    groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        return {"groups": []}
    out = []
    for g in groups:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("id", "")).strip()
        label = str(g.get("label", "")).strip()
        opts = g.get("options")
        if not isinstance(opts, list):
            opts = []
        clean_opts = []
        for o in opts:
            t = str(o).strip()
            if t and t not in clean_opts:
                clean_opts.append(t[:200])
        if not label:
            continue
        out.append({"id": gid or label[:64], "label": label[:120], "options": clean_opts})
    return {"groups": out}


def all_consumable_labels() -> set[str]:
    s: set[str] = set()
    for g in load_consumables_catalog()["groups"]:
        for o in g.get("options", []):
            s.add(str(o))
    return s

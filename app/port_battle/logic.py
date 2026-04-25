"""Bridge FastAPI ↔ legacy `Port Battle Python/Port Battle Calculator.py` (no Tk required for API calls)."""

from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_LEGACY_DIR = Path(__file__).resolve().parent.parent.parent / "Port Battle Python"
_CALC_PATH = _LEGACY_DIR / "Port Battle Calculator.py"
_SETTINGS_PATH = _LEGACY_DIR / "port_planner_settings.json"


class PortBattleProgramMissing(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _load_calculator_module():
    if not _CALC_PATH.is_file():
        raise PortBattleProgramMissing(
            f"Calculator not found at {_CALC_PATH}. Add the 'Port Battle Python' folder to the project root."
        )
    spec = importlib.util.spec_from_file_location("wosb_port_battle_calc", _CALC_PATH)
    if spec is None or spec.loader is None:
        raise PortBattleProgramMissing("Could not load calculator module spec.")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_port_names() -> list[str]:
    """Sorted port names from the embedded calculator database (for web UI pickers)."""
    mod = _load_calculator_module()
    db = mod.get_port_database()
    names = [str(p.get("name", "")).strip() for p in db if p.get("name")]
    return sorted(set(names), key=str.casefold)


def lookup_port(name: str) -> dict[str, Any] | None:
    """Return one port row from the calculator DB (name, rate_text, rate_num, pvp_size), or None."""
    key = (name or "").strip().casefold()
    if not key:
        return None
    mod = _load_calculator_module()
    for p in mod.get_port_database():
        if str(p.get("name", "")).strip().casefold() == key:
            return dict(p)
    return None


def get_default_settings_json() -> dict[str, Any]:
    """Return saved GUI settings if present, else a sensible starter object."""
    if _SETTINGS_PATH.is_file():
        try:
            return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {
        "days": "7",
        "windows": {"TIF": "18:00-20:00", "BWC": "18:00-20:00", "SVA": "22:00-00:00", "LP": "18:00-20:00"},
        "ownership": {
            "TIF": "Charleston, Fiji, Northside",
            "BWC": "Aruba, Severoangelsk",
            "SVA": "North Bastion",
            "LP": "",
        },
        "transition_rows": [{"port": "Aruba", "state": "remaining", "value": "1d 2h 32m"}],
    }


def _split_main_schedule_report(report: str) -> tuple[str, str]:
    """
    `create_report` returns battles + placement in one string, separated by the
    placement section heading. Used to expose two plain-text reports to the API.
    """
    key = "PROTECTION TIMER PLACEMENT"
    idx = report.find(key)
    if idx == -1:
        return report.rstrip(), ""
    battles = report[:idx].rstrip()
    placement = report[idx:].lstrip()
    return battles, placement


def _build_report_schedule(
    mod,
    days: int,
    guild_windows: dict,
    port_database: list,
    port_owners: dict,
    transition_states: dict,
    now_dt,
) -> dict[str, Any]:
    """JSON-serializable battle + placement schedule for the web UI (mirrors create_report grouping)."""
    from datetime import timedelta

    events, _ = mod.build_event_schedule(
        now_dt, days, guild_windows, port_database, port_owners, transition_states
    )
    start_date = now_dt.date()
    events_by_date: dict = {}
    for event in events:
        events_by_date.setdefault(event["window_start"].date(), []).append(event)

    battle_days: list[dict[str, Any]] = []
    placement_days: list[dict[str, Any]] = []
    for i in range(days):
        day_value = start_date + timedelta(days=i)
        raw = events_by_date.get(day_value, [])

        day_b = sorted(raw, key=lambda item: item["window_start"])
        battles: list[dict[str, Any]] = []
        for event in day_b:
            ws = event["window_start"]
            battles.append(
                {
                    "port": event["port_name"],
                    "rate": event["rate_text"],
                    "pvp": event["pvp_size"],
                    "time_label": ws.strftime("%H:%M"),
                }
            )
        battle_days.append(
            {
                "weekday": day_value.strftime("%A"),
                "date": day_value.strftime("%Y-%m-%d"),
                "free_night": len(day_b) == 0,
                "battles": battles,
            }
        )

        day_p = sorted(raw, key=lambda item: item["place_at"])
        rows: list[dict[str, Any]] = []
        for event in day_p:
            pa = event["place_at"]
            rows.append(
                {
                    "port": event["port_name"],
                    "timer_h": int(event["timer_hours"]),
                    "at_label": mod.fmt(pa),
                }
            )
        placement_days.append(
            {
                "weekday": day_value.strftime("%A"),
                "date": day_value.strftime("%Y-%m-%d"),
                "no_action": len(day_p) == 0,
                "rows": rows,
            }
        )

    return {"battle_days": battle_days, "placement_days": placement_days}


def run_generation(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Run the same pipeline as the desktop "Generate schedule" button.

    `payload` matches `port_planner_settings.json` shape plus int `days`:
    - days: int 1..31
    - windows: { "TIF": "HH:MM-HH:MM", ... }
    - ownership: { "TIF": "Port, Port", ... }
    - transition_rows: [ { "port", "state", "value" }, ... ]
    """
    mod = _load_calculator_module()
    from datetime import datetime

    days = int(payload["days"])
    if days < 1 or days > 31:
        raise ValueError("Days must be between 1 and 31.")

    guild_windows = {}
    for guild in mod.GUILDS:
        if guild not in payload.get("windows", {}):
            raise ValueError(f"Missing attack window for {guild}.")
        guild_windows[guild] = mod.parse_window(str(payload["windows"][guild]).strip())

    port_database = mod.get_port_database()
    ownership_inputs = {g: str(payload.get("ownership", {}).get(g, "")) for g in mod.GUILDS}
    port_owners = mod.parse_ownership(ownership_inputs, port_database)

    lines = []
    for row in payload.get("transition_rows") or []:
        port = str(row.get("port", "")).strip()
        if not port:
            continue
        state = str(row.get("state", "")).strip().lower()
        value = str(row.get("value", "")).strip()
        if state in ("remaining", "available_in") and not value:
            raise ValueError(f"{port}: enter a time value (e.g. 9h 30m or 1d 4h).")
        if state == "available" and not value:
            value = "now"
        lines.append(f"{port},{state},{value}")
    transition_csv = "\n".join(lines)
    transition_states = mod.parse_transition_state(transition_csv, port_database)

    now_dt = datetime.now(mod.GMT_MINUS_6)
    report = mod.create_report(
        days, guild_windows, port_database, port_owners, transition_states, now_dt
    )
    transition_report = mod.create_transition_report(
        now_dt, transition_states, port_database, port_owners, guild_windows
    )
    report_battles, report_placement = _split_main_schedule_report(report)
    full_report = report + "\n\n" + transition_report
    discord_snippet = mod.create_discord_battle_snippet(
        days, guild_windows, port_database, port_owners, transition_states, now_dt
    )
    report_schedule = _build_report_schedule(
        mod, days, guild_windows, port_database, port_owners, transition_states, now_dt
    )
    return {
        "ok": True,
        "report": full_report,
        "report_battles": report_battles,
        "report_placement": report_placement,
        "report_schedule": report_schedule,
        "report_transition": transition_report,
        "discord": discord_snippet,
        "generated_at_gmt6": now_dt.isoformat(),
    }

from datetime import datetime, timedelta, timezone
import json
import os
import sys
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


class HoverTip:
    """Small hover tooltip (delay then show; hides when pointer leaves)."""

    def __init__(self, widget, text, app, delay_ms=500, wraplength=400):
        self.widget = widget
        self.text = text
        self.app = app
        self.delay_ms = delay_ms
        self.wraplength = wraplength
        self._tip = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, event=None):
        self._hide()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _hide(self, event=None):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self._tip:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

    def _show(self):
        self._after_id = None
        if not self.widget.winfo_exists():
            return
        tb = self.app._theme
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try:
            tw.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        lbl = tk.Label(
            tw,
            text=self.text,
            justify="left",
            wraplength=self.wraplength,
            background=tb["input"],
            foreground=tb["fg"],
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
        )
        lbl.pack()
        tw.update_idletasks()
        th = tw.winfo_reqheight()
        twy = y
        if twy + th > self.widget.winfo_toplevel().winfo_screenheight() - 24:
            twy = max(8, self.widget.winfo_rooty() - th - 6)
        tw.geometry(f"+{x}+{int(twy)}")


_REPORT_SECTION_TITLES = frozenset(
    {
        "PORT BATTLES BY DAY (GMT-6)",
        "PROTECTION TIMER PLACEMENT",
        "TRANSITION WEEK ACTIONS",
        "TRANSITION CHECKLIST (ORDERED)",
    }
)
_WEEKDAY_LINE_PREFIXES = (
    "Monday ",
    "Tuesday ",
    "Wednesday ",
    "Thursday ",
    "Friday ",
    "Saturday ",
    "Sunday ",
)


def report_output_line_tags(line, discord=False):
    """Return Text tag names for one line (clipboard copy ignores tags)."""
    if discord:
        if not line.strip():
            return ()
        if line.startswith("**__") and "__**" in line:
            return ("out_h1",)
        if line.startswith("  "):
            return ("out_line", "out_indent")
        return ("out_line",)

    if not line.strip():
        return ()
    st = line.strip()
    if st and all(ch == "-" for ch in st):
        return ("out_rule",)
    if line in _REPORT_SECTION_TITLES:
        return ("out_h1",)
    if any(line.startswith(p) for p in _WEEKDAY_LINE_PREFIXES) and len(line) < 48:
        return ("out_day",)
    if line.startswith("  ") and "FREE" in line.upper():
        return ("out_dim", "out_indent")
    if line.startswith("  "):
        return ("out_line", "out_indent")
    if line.startswith("Step "):
        return ("out_step",)
    if line.startswith("For each open") or line.startswith("Use these one-time"):
        return ("out_dim",)
    if line.startswith("No transition") or line.startswith("No checklist"):
        return ("out_dim",)
    if " | " in line and not line.startswith(" ") and "Next action" not in line:
        if "Owner window" not in line and "Suggested placement" not in line:
            return ("out_port",)
    if line.startswith("  Next action") or line.startswith("  Owner window") or line.startswith(
        "  Suggested"
    ):
        return ("out_note", "out_indent")
    return ("out_line",)


def quick_guide_text():
    return (
        "PORT BATTLE PLANNER — QUICK GUIDE\n"
        "==================================\n\n"
        "All times use a fixed GMT-6 offset (no daylight rules).\n\n"
        "WINDOWS & OWNERSHIP\n"
        "--------------------\n"
        "• Days to generate — how many calendar days of schedule to build.\n"
        "• Each guild has an attack window (HH:MM-HH:MM). Ports only open in those windows.\n"
        "• Ownership — comma-separated port names per guild (used to label who holds what).\n\n"
        "TRANSITION WEEK (PER PORT)\n"
        "--------------------------\n"
        "One row per port you care about this week.\n"
        "• Port — pick from the built-in list (Refresh if the DB changed).\n"
        "• State:\n"
        "  - remaining — protection still running; value is time left (e.g. 1d 4h).\n"
        "  - available — you may place protection now; value is usually \"now\".\n"
        "  - available_in — reprotection cooldown; value is time until you can place again.\n"
        "• Add row / Remove last row — edit the table size.\n\n"
        "ACTIONS\n"
        "-------\n"
        "• Generate schedule — fills the Output and Discord panes from your inputs.\n"
        "• Copy output — full text report to the clipboard.\n"
        "• Copy Discord — announcement block with Discord timestamps (<t:…:F>).\n\n"
        "SETTINGS\n"
        "--------\n"
        "Your inputs are saved when you close the app (JSON beside the script or exe).\n\n"
        "TIP: Pause the mouse over any field for a short hover tip.\n"
    )


GMT_MINUS_6 = timezone(timedelta(hours=-6))
GUILDS = ["TIF", "BWC", "SVA", "LP"]
TIMER_OPTIONS = [12, 36, 60, 84]

DEFAULT_WINDOWS = {
    "TIF": "18:00-20:00",
    "BWC": "18:00-20:00",
    "SVA": "22:00-00:00",
    "LP": "18:00-20:00",
}

DEFAULT_OWNERSHIP = {
    "TIF": "Charleston, Fiji, Northside",
    "BWC": "Aruba, Severoangelsk",
    "SVA": "North Bastion",
    "LP": "",
}

# Built-in port database (not editable in UI). Update this list if ports change.
_PORT_DATABASE_LINES = [
    "Oneg,Rate2,10v10",
    "Everston Bay,Rate2,40v40",
    "Severoangelsk,Rate4,20v20",
    "Northside,Rate5,20v20",
    "North Bastion,Rate4,15v15",
    "Gray Island,Rate1,10v10",
    "Aruba,Rate2,20v20",
    "Gelbion,Rate3,20v20",
    "Nisogra,Rate3,10v10",
    "Nevis,Rate1,20v20",
    "Thermopylae,Rate1,20v20",
    "Fiji,Rate6,15v15",
    "Cursed City,Rate3,15v15",
    "West Bastion,Rate1,20v20",
    "Masadora,Rate1,10v10",
    "Bridgetown,Rate1,20v20",
    "Navidad,Rate1,40v40",
    "Laguna Blanco,Rate1,20v20",
    "Charleston,Rate1,15v15",
    "Devios,Rate1,15v15",
    "Los Catuano,Rate6,15v15",
    "South Bastion,Rate5,20v20",
    "San Martinas,Rate1,15v15",
    "San Cristobel,Rate4,20v20",
    "Bord Radel,Rate1,20v20",
]
PORT_DATABASE_TEXT = "\n".join(_PORT_DATABASE_LINES)

_BUILTIN_PORT_DATABASE = None


def _app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _windows_set_per_monitor_dpi_aware():
    """Sharper text on scaled displays: call before tk.Tk()."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError, ValueError):
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


SETTINGS_FILE = os.path.join(_app_base_dir(), "port_planner_settings.json")
DEFAULT_TRANSITION_ROWS = [
    {"port": "Aruba", "state": "remaining", "value": "1d 4h"},
    {"port": "Severoangelsk", "state": "remaining", "value": "1d 7h"},
    {"port": "Northside", "state": "available", "value": "now"},
    {"port": "North Bastion", "state": "remaining", "value": "2d 15h"},
    {"port": "Fiji", "state": "available_in", "value": "9h 30m"},
    {"port": "Charleston", "state": "remaining", "value": "3d 10h"},
]

TRANSITION_STATES = ("remaining", "available", "available_in")


def fmt(dt):
    return dt.strftime("%a %Y-%m-%d %H:%M GMT-6")


def discord_ts(dt):
    return f"<t:{int(dt.timestamp())}:F>"


def parse_time(text_value):
    text_value = text_value.strip()
    if ":" not in text_value:
        raise ValueError(f"Invalid time '{text_value}'. Use HH:MM.")
    hour_text, minute_text = text_value.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 24:
        raise ValueError(f"Hour out of range in '{text_value}'.")
    if minute < 0 or minute > 59:
        raise ValueError(f"Minute out of range in '{text_value}'.")
    if hour == 24 and minute != 0:
        raise ValueError("24 is only valid as 24:00.")
    return hour, minute


def parse_window(text_value):
    if "-" not in text_value:
        raise ValueError(f"Invalid window '{text_value}'. Use HH:MM-HH:MM.")
    start_text, end_text = text_value.split("-", 1)
    start_hour, start_minute = parse_time(start_text)
    end_hour, end_minute = parse_time(end_text)
    return (start_hour, start_minute), (end_hour, end_minute)


def parse_port_list(text_value):
    if not text_value.strip():
        return []
    return [item.strip() for item in text_value.split(",") if item.strip()]


def parse_rate(rate_text):
    text = rate_text.strip().lower()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        raise ValueError(f"Rate '{rate_text}' must include a number (ex: Rate 1).")
    return int(digits)


def parse_port_database(db_text):
    ports = []
    seen = set()
    for raw_line in db_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
        else:
            parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            raise ValueError(
                f"Invalid port DB line '{line}'. Use either "
                f"'Port Name | Rate X | 15v15' or 'Port Name,RateX,15v15'."
            )
        name, rate_text, pvp_size = parts
        if not name:
            raise ValueError("Port name cannot be blank in DB.")
        if name in seen:
            raise ValueError(f"Duplicate port in DB: {name}")
        ports.append(
            {
                "name": name,
                "rate_text": rate_text,
                "rate_num": parse_rate(rate_text),
                "pvp_size": pvp_size,
            }
        )
        seen.add(name)
    if not ports:
        raise ValueError("Port database is empty.")
    return ports


def get_port_database():
    global _BUILTIN_PORT_DATABASE
    if _BUILTIN_PORT_DATABASE is None:
        _BUILTIN_PORT_DATABASE = parse_port_database(PORT_DATABASE_TEXT)
    return _BUILTIN_PORT_DATABASE


def parse_ownership(ownership_inputs, port_database):
    port_lookup = {p["name"] for p in port_database}
    owners = {}
    for guild, raw in ownership_inputs.items():
        for port in parse_port_list(raw):
            if port not in port_lookup:
                raise ValueError(
                    f"Ownership references unknown port '{port}'. Add it to Port Database first."
                )
            if port in owners:
                raise ValueError(
                    f"Port '{port}' assigned to multiple guilds ({owners[port]} and {guild})."
                )
            owners[port] = guild
    return owners


def parse_duration_text(duration_text):
    text = duration_text.strip().lower()
    if text in ("now", "0", "0h", "0m", "0d"):
        return timedelta(0)
    total_minutes = 0
    current = ""
    saw_unit = False
    for char in text:
        if char.isdigit():
            current += char
            continue
        if char in ("d", "h", "m") and current:
            value = int(current)
            if char == "d":
                total_minutes += value * 24 * 60
            elif char == "h":
                total_minutes += value * 60
            else:
                total_minutes += value
            current = ""
            saw_unit = True
    if not saw_unit:
        raise ValueError(
            f"Invalid duration '{duration_text}'. Examples: '1d 4h', '9h 30m', 'now'."
        )
    return timedelta(minutes=total_minutes)


def parse_transition_state(text_value, port_database):
    valid_ports = {p["name"] for p in port_database}
    states = {}
    for raw_line in text_value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            raise ValueError(
                f"Invalid transition line '{line}'. Use: Port, state, value"
            )
        port_name, state_name, value = parts
        if port_name not in valid_ports:
            raise ValueError(f"Unknown port in transition data: {port_name}")
        state_name = state_name.lower()
        if state_name not in ("remaining", "available", "available_in"):
            raise ValueError(
                f"Invalid state '{state_name}' for {port_name}. Use remaining/available/available_in."
            )
        if state_name == "available":
            delta = timedelta(0)
        else:
            delta = parse_duration_text(value)
        states[port_name] = {"state": state_name, "delta": delta}
    return states


def timer_for_rate(rate_num):
    # New rule: Rate 1/2 should happen as little as possible.
    if rate_num in (1, 2):
        return 84
    return 60


def cycle_days_from_timer(timer_hours):
    # 12=>1, 36=>2, 60=>3, 84=>4 (roughly one open night every N days)
    mapping = {12: 1, 36: 2, 60: 3, 84: 4}
    return mapping.get(timer_hours, 1)


def get_window_for_date(port_owner, date_value, guild_windows):
    (start_hour, start_minute), (end_hour, end_minute) = guild_windows[port_owner]
    start = datetime(
        date_value.year,
        date_value.month,
        date_value.day,
        start_hour,
        start_minute,
        tzinfo=GMT_MINUS_6,
    )
    if end_hour == 24 and end_minute == 0:
        end = start.replace(hour=0, minute=0) + timedelta(days=1)
    else:
        end = start.replace(hour=end_hour, minute=end_minute)
    return start, end


def next_window_close_at_or_after(port_owner, anchor_dt, guild_windows):
    for offset in range(0, 8):
        day_value = (anchor_dt + timedelta(days=offset)).date()
        _, window_end = get_window_for_date(port_owner, day_value, guild_windows)
        if window_end >= anchor_dt:
            return window_end
    # Fallback should never happen with normal windows.
    return anchor_dt


def next_window_close_after(port_owner, anchor_dt, guild_windows):
    return next_window_close_at_or_after(
        port_owner, anchor_dt + timedelta(seconds=1), guild_windows
    )


def next_window_start_at_or_after(port_owner, anchor_dt, guild_windows):
    for offset in range(0, 8):
        day_value = (anchor_dt + timedelta(days=offset)).date()
        window_start, _ = get_window_for_date(port_owner, day_value, guild_windows)
        if window_start >= anchor_dt:
            return window_start
    return anchor_dt


def first_battle_moment_at_or_after(port_owner, anchor_dt, guild_windows):
    """First instant the port can be attacked (GMT-6).

    If protection ends during the attack window, the remainder of that window
    is still valid (first attackable moment = anchor when anchor lies inside the window).
    """
    for offset in range(0, 10):
        day_value = (anchor_dt + timedelta(days=offset)).date()
        window_start, window_end = get_window_for_date(port_owner, day_value, guild_windows)
        if anchor_dt >= window_end:
            continue
        if anchor_dt <= window_start:
            return window_start
        return anchor_dt
    return next_window_start_at_or_after(port_owner, anchor_dt, guild_windows)


def window_key_for_owner(owner, guild_windows):
    (sh, sm), (eh, em) = guild_windows[owner]
    return f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"


def next_window_start_after(port_owner, anchor_dt, guild_windows):
    return next_window_start_at_or_after(port_owner, anchor_dt + timedelta(seconds=1), guild_windows)


def build_event_schedule(now_dt, days, guild_windows, port_database, port_owners, transition_states):
    horizon_end = now_dt + timedelta(days=days)
    port_map = {p["name"]: p for p in port_database}
    state_map = {}

    for port_name, owner in port_owners.items():
        port = port_map[port_name]
        timer_hours = timer_for_rate(port["rate_num"])
        transition = transition_states.get(port_name, {"state": "available", "delta": timedelta(0)})
        state_name = transition["state"]
        delta = transition["delta"]

        if state_name == "remaining":
            protection_end = now_dt + delta
            next_open = first_battle_moment_at_or_after(owner, protection_end, guild_windows)
            earliest_reprotect = next_window_close_after(owner, protection_end, guild_windows)
        elif state_name == "available_in":
            # Cooldown on *placing* protection (e.g. must wait until tonight's window ends).
            # delta = time from now until you are allowed to place a protection timer.
            # That moment is earliest_reprotect. The port can still be open for battle now;
            # cooldown only blocks re-protection placement.
            cooldown_ends = now_dt + delta
            next_open = first_battle_moment_at_or_after(owner, now_dt, guild_windows)
            earliest_reprotect = cooldown_ends
        else:
            next_open = first_battle_moment_at_or_after(owner, now_dt, guild_windows)
            earliest_reprotect = now_dt

        state_map[port_name] = {
            "owner": owner,
            "timer_hours": timer_hours,
            "rate_num": port["rate_num"],
            "rate_text": port["rate_text"],
            "pvp_size": port["pvp_size"],
            "next_open": next_open,
            "earliest_reprotect": earliest_reprotect,
        }

    events = []
    first_placement_by_port = {}

    while True:
        active = [
            (name, info["next_open"])
            for name, info in state_map.items()
            if info["next_open"] <= horizon_end
        ]
        if not active:
            break

        current_time = min(ts for _, ts in active)
        opening_names = [name for name, ts in active if ts == current_time]

        # Rule: if possible, avoid multiple Rate1/2 in same window at same time.
        high_by_window = {}
        for name in opening_names:
            info = state_map[name]
            if info["rate_num"] in (1, 2):
                key = window_key_for_owner(info["owner"], guild_windows)
                high_by_window.setdefault(key, []).append(name)

        for _, conflict_names in high_by_window.items():
            if len(conflict_names) <= 1:
                continue
            keep_name = sorted(conflict_names)[0]
            for name in sorted(conflict_names):
                if name == keep_name:
                    continue
                owner = state_map[name]["owner"]
                state_map[name]["next_open"] = next_window_start_after(
                    owner, state_map[name]["next_open"], guild_windows
                )

        opening_names = [
            name
            for name, ts in [
                (n, info["next_open"])
                for n, info in state_map.items()
                if info["next_open"] <= horizon_end
            ]
            if ts == current_time
        ]
        if not opening_names:
            continue

        for name in sorted(opening_names):
            info = state_map[name]
            window_start = info["next_open"]
            _, window_end = get_window_for_date(info["owner"], window_start.date(), guild_windows)
            # Re-protection can be placed after at least one attack window has passed
            # since protection ended; placing at this open window close satisfies that.
            place_at = max(window_end, info["earliest_reprotect"])
            protection_end = place_at + timedelta(hours=info["timer_hours"])
            next_open = first_battle_moment_at_or_after(
                info["owner"], protection_end, guild_windows
            )
            earliest_reprotect = next_window_close_after(info["owner"], protection_end, guild_windows)

            events.append(
                {
                    "port_name": name,
                    "owner": info["owner"],
                    "rate_text": info["rate_text"],
                    "pvp_size": info["pvp_size"],
                    "window_start": window_start,
                    "place_at": place_at,
                    "timer_hours": info["timer_hours"],
                }
            )
            if name not in first_placement_by_port:
                first_placement_by_port[name] = place_at

            state_map[name]["next_open"] = next_open
            state_map[name]["earliest_reprotect"] = earliest_reprotect

    return events, first_placement_by_port


def create_report(days, guild_windows, port_database, port_owners, transition_states=None, now_dt=None):
    if transition_states is None:
        transition_states = {}
    if now_dt is None:
        now_dt = datetime.now(GMT_MINUS_6)

    start_date = now_dt.date()
    events, _ = build_event_schedule(
        now_dt, days, guild_windows, port_database, port_owners, transition_states
    )
    events_by_date = {}
    for event in events:
        events_by_date.setdefault(event["window_start"].date(), []).append(event)

    lines = []
    lines.append("PORT BATTLES BY DAY (GMT-6)")
    lines.append("-" * 78)
    for i in range(days):
        day_value = start_date + timedelta(days=i)
        day_entries = sorted(events_by_date.get(day_value, []), key=lambda item: item["window_start"])
        lines.append(day_value.strftime("%A %Y-%m-%d"))
        if not day_entries:
            lines.append("  FREE NIGHT")
            lines.append("")
            continue
        for event in day_entries:
            lines.append(
                f"  {event['port_name']} - {event['rate_text']} - {event['pvp_size']} - "
                f"{discord_ts(event['window_start'])}"
            )
        lines.append("")

    lines.append("")
    lines.append("PROTECTION TIMER PLACEMENT")
    lines.append("-" * 78)
    lines.append("For each open night: place timer at/after window close.")
    lines.append("")
    for i in range(days):
        day_value = start_date + timedelta(days=i)
        day_entries = sorted(events_by_date.get(day_value, []), key=lambda item: item["place_at"])
        lines.append(day_value.strftime("%A %Y-%m-%d"))
        if not day_entries:
            lines.append("  - No action required.")
            lines.append("")
            continue
        for event in day_entries:
            lines.append(
                f"  - {event['port_name']:<20} place {event['timer_hours']:>2}h at "
                f"{fmt(event['place_at'])} ({discord_ts(event['place_at'])})"
            )
        lines.append("")
    return "\n".join(lines)


def create_discord_battle_snippet(
    days, guild_windows, port_database, port_owners, transition_states=None, now_dt=None
):
    """Discord-friendly battles: weekday only, ports grouped under each day, Unix timestamps."""
    if transition_states is None:
        transition_states = {}
    if now_dt is None:
        now_dt = datetime.now(GMT_MINUS_6)

    start_date = now_dt.date()
    events, _ = build_event_schedule(
        now_dt, days, guild_windows, port_database, port_owners, transition_states
    )
    events_by_date = {}
    for event in events:
        events_by_date.setdefault(event["window_start"].date(), []).append(event)

    lines = []
    for i in range(days):
        day_value = start_date + timedelta(days=i)
        day_name = day_value.strftime("%A")
        day_entries = sorted(events_by_date.get(day_value, []), key=lambda item: item["window_start"])
        lines.append(f"**__{day_name}__**")
        if not day_entries:
            lines.append("  FREE")
        else:
            for event in day_entries:
                lines.append(
                    f"  {event['port_name']} | {discord_ts(event['window_start'])}"
                )
        lines.append("")
    return "\n".join(lines).rstrip()


def create_transition_report(now_dt, transition_states, port_database, port_owners, guild_windows):
    port_map = {p["name"]: p for p in port_database}
    _, first_placement_by_port = build_event_schedule(
        now_dt, 31, guild_windows, port_database, port_owners, transition_states
    )
    checklist = []
    lines = []
    lines.append("TRANSITION WEEK ACTIONS")
    lines.append("-" * 78)
    lines.append("Use these one-time actions to move current timers into target rhythm.")
    lines.append("")

    for port_name in sorted(transition_states.keys()):
        if port_name not in port_owners:
            continue
        port = port_map[port_name]
        owner = port_owners[port_name]
        state = transition_states[port_name]
        target_timer = timer_for_rate(port["rate_num"])
        action_anchor = now_dt

        if state["state"] == "remaining":
            ready_at = now_dt + state["delta"]
            action_anchor = ready_at
            lines.append(
                f"{port_name} - {port['rate_text']} - {port['pvp_size']} | "
                f"current protection ends {fmt(ready_at)}"
            )
            lines.append(
                f"  Next action: first open window after protection end is battle-eligible; "
                f"place {target_timer}h after that window closes."
            )
        elif state["state"] == "available_in":
            ready_at = now_dt + state["delta"]
            action_anchor = ready_at
            lines.append(
                f"{port_name} - {port['rate_text']} - {port['pvp_size']} | "
                f"may place protection after {fmt(ready_at)} (reprotection cooldown)"
            )
            lines.append(
                f"  Next action: at/after that time, place {target_timer}h (usually at window close)."
            )
        else:
            lines.append(
                f"{port_name} - {port['rate_text']} - {port['pvp_size']} | timer available now"
            )
            lines.append(
                f"  Next action: place {target_timer}h now or at next window close."
            )

        window_start, window_end = get_window_for_date(owner, now_dt.date(), guild_windows)
        suggested_place_at = first_placement_by_port.get(
            port_name, next_window_close_at_or_after(owner, action_anchor, guild_windows)
        )
        checklist.append(
            {
                "action_time": suggested_place_at,
                "port_name": port_name,
                "rate_text": port["rate_text"],
                "pvp_size": port["pvp_size"],
                "timer": target_timer,
            }
        )
        lines.append(
            f"  Owner window ({owner}): {window_start.strftime('%H:%M')}-{window_end.strftime('%H:%M')} GMT-6"
        )
        lines.append(
            f"  Suggested placement checkpoint: {fmt(suggested_place_at)}"
        )
        lines.append("")

    if len(lines) <= 4:
        lines.append("No transition data entered.")
        lines.append("")

    lines.append("")
    lines.append("TRANSITION CHECKLIST (ORDERED)")
    lines.append("-" * 78)
    if not checklist:
        lines.append("No checklist items.")
        lines.append("")
        return "\n".join(lines)

    for step, item in enumerate(sorted(checklist, key=lambda x: x["action_time"]), start=1):
        lines.append(
            f"Step {step}: {item['port_name']} - {item['rate_text']} - {item['pvp_size']} - "
            f"place {item['timer']}h at {fmt(item['action_time'])}"
        )
    lines.append("")
    return "\n".join(lines)


class PortPlannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Port Battle Planner")
        self.root.geometry("1360x940")
        self.root.minsize(1020, 820)

        self._banner_photo_ref = None
        self._configure_styles()
        self.root.configure(bg=self._theme["root"])
        self._setup_help_menu()

        self._try_load_banner()

        main = ttk.Frame(root, padding=(14, 12))
        main.pack(fill="both", expand=True)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(4, weight=1)

        hdr = ttk.Frame(main)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(hdr, text="Port Battle Planner (GMT-6)", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            hdr,
            text="Hover fields for quick tips — Help → Quick guide for the full walkthrough.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        lf_top = ttk.LabelFrame(main, text="Windows & ownership", padding=(12, 10))
        lf_top.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        lf_top.grid_columnconfigure(0, weight=0)
        lf_top.grid_columnconfigure(1, weight=1)
        self.lf_top = lf_top

        top_left = ttk.Frame(lf_top)
        top_left.grid(row=0, column=0, sticky="nw", padx=(0, 24))
        top_right = ttk.Frame(lf_top)
        self.top_right = top_right
        top_right.grid(row=0, column=1, sticky="nsew")
        top_right.grid_columnconfigure(1, weight=1)

        ttk.Label(top_left, text="Days to generate:").grid(row=0, column=0, sticky="e", padx=(0, 8), pady=2)
        self.days_var = tk.StringVar(value="7")
        self.days_entry = ttk.Entry(top_left, textvariable=self.days_var, width=8)
        self.days_entry.grid(row=0, column=1, sticky="w", pady=2)

        self.window_vars = {}
        self._guild_window_entries = {}
        for i, guild in enumerate(GUILDS):
            r = i + 1
            ttk.Label(top_left, text=f"{guild} window:").grid(row=r, column=0, sticky="e", padx=(0, 8), pady=3)
            var = tk.StringVar(value=DEFAULT_WINDOWS[guild])
            ent = ttk.Entry(top_left, textvariable=var, width=18)
            ent.grid(row=r, column=1, sticky="w", pady=3)
            self.window_vars[guild] = var
            self._guild_window_entries[guild] = ent
        ttk.Label(top_left, text="(HH:MM-HH:MM)", style="Muted.TLabel").grid(
            row=len(GUILDS) + 1, column=1, sticky="w", pady=(2, 0)
        )

        ttk.Label(
            top_right,
            text="Ownership (comma-separated port names)",
            style="Subheader.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.ownership_vars = {}
        self._ownership_entries = {}
        for idx, guild in enumerate(GUILDS, start=1):
            ttk.Label(top_right, text=f"{guild}:", width=5, anchor="e").grid(
                row=idx, column=0, sticky="e", padx=(0, 8), pady=3
            )
            var = tk.StringVar(value=DEFAULT_OWNERSHIP[guild])
            oent = ttk.Entry(top_right, textvariable=var)
            oent.grid(row=idx, column=1, sticky="ew", pady=3)
            self.ownership_vars[guild] = var
            self._ownership_entries[guild] = oent

        lf_trans = ttk.LabelFrame(main, text="Transition week (per port)", padding=(12, 10))
        lf_trans.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        lf_trans.grid_columnconfigure(0, weight=2)
        lf_trans.grid_columnconfigure(1, weight=1)
        self.lf_trans = lf_trans

        trans_wrap = ttk.Frame(lf_trans)
        trans_wrap.grid(row=0, column=0, columnspan=2, sticky="ew")
        trans_wrap.grid_columnconfigure(0, weight=2)
        trans_wrap.grid_columnconfigure(1, weight=1)

        trans_left = ttk.Frame(trans_wrap)
        trans_left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))

        self.transition_form = ttk.Frame(trans_left)
        self.transition_form.pack(fill="x", anchor="nw")
        for col, w in ((0, 2), (1, 1), (2, 2)):
            self.transition_form.grid_columnconfigure(col, weight=w, uniform="transcol")

        self._lbl_trans_port = ttk.Label(
            self.transition_form, text="Port", style="TableHeader.TLabel"
        )
        self._lbl_trans_port.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 6))
        self._lbl_trans_state = ttk.Label(
            self.transition_form, text="State", style="TableHeader.TLabel"
        )
        self._lbl_trans_state.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=(0, 6))
        self._lbl_trans_time = ttk.Label(
            self.transition_form, text="Time value", style="TableHeader.TLabel"
        )
        self._lbl_trans_time.grid(row=0, column=2, sticky="w", pady=(0, 6))

        btn_row = ttk.Frame(trans_left)
        btn_row.pack(fill="x", pady=(10, 0))
        self.btn_trans_add = ttk.Button(btn_row, text="Add row", command=self._transition_add_row, width=11)
        self.btn_trans_add.pack(side="left", padx=(0, 8))
        self.btn_trans_remove = ttk.Button(
            btn_row, text="Remove last row", command=self._transition_remove_row, width=16
        )
        self.btn_trans_remove.pack(side="left", padx=(0, 8))
        self.btn_trans_refresh = ttk.Button(
            btn_row, text="Refresh port names", command=self._transition_refresh_ports, width=20
        )
        self.btn_trans_refresh.pack(side="left")

        legend = ttk.LabelFrame(trans_wrap, text="State meanings", padding=(10, 8))
        legend.grid(row=0, column=1, sticky="ne")
        self.legend_frame = legend
        guide_wrap = 280
        ttk.Label(
            legend,
            text="remaining - protection time left",
            wraplength=guide_wrap,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        ttk.Label(
            legend,
            text="available - you may place protection now",
            wraplength=guide_wrap,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        ttk.Label(
            legend,
            text=(
                "available_in - time until you may place protection "
                "(reprotection cooldown, e.g. until the attack window ends)"
            ),
            wraplength=guide_wrap,
            justify="left",
        ).pack(anchor="w")

        self.transition_row_widgets = []
        self._rebuild_transition_rows(DEFAULT_TRANSITION_ROWS)

        btn_bar = ttk.Frame(main)
        btn_bar.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.btn_generate = ttk.Button(
            btn_bar, text="Generate schedule", command=self.generate_output, width=20
        )
        self.btn_generate.pack(side="left", padx=(0, 10))
        self.btn_copy_report = ttk.Button(btn_bar, text="Copy output", command=self.copy_output, width=14)
        self.btn_copy_report.pack(side="left", padx=(0, 8))
        self.btn_copy_discord = ttk.Button(
            btn_bar, text="Copy Discord", command=self.copy_discord_output, width=14
        )
        self.btn_copy_discord.pack(side="left")

        outputs = ttk.Frame(main)
        outputs.grid(row=4, column=0, sticky="nsew", pady=(0, 0))
        outputs.grid_columnconfigure(0, weight=3)
        outputs.grid_columnconfigure(1, weight=2)
        outputs.grid_rowconfigure(0, weight=1)

        out_lf = ttk.LabelFrame(outputs, text="Output", padding=(8, 6))
        self.out_lf = out_lf
        out_lf.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        out_lf.grid_rowconfigure(0, weight=1)
        out_lf.grid_columnconfigure(0, weight=1)

        self.output = scrolledtext.ScrolledText(
            out_lf, wrap="word", font=("Consolas", 12), padx=10, pady=10, height=20
        )
        self.output.grid(row=0, column=0, sticky="nsew")
        self.output.insert(
            "1.0",
            "Edit windows, ownership, and transition rows above, then click Generate schedule.",
        )
        self.output.configure(state="disabled")

        disc_lf = ttk.LabelFrame(outputs, text="Discord announcement", padding=(8, 6))
        self.disc_lf = disc_lf
        disc_lf.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        disc_lf.grid_rowconfigure(0, weight=1)
        disc_lf.grid_columnconfigure(0, weight=1)

        self.discord_output = scrolledtext.ScrolledText(
            disc_lf, wrap="word", font=("Consolas", 12), padx=10, pady=10, height=20
        )
        self.discord_output.grid(row=0, column=0, sticky="nsew")
        self.discord_output.insert(
            "1.0",
            "Weekday + grouped ports with Discord timestamps. Generated with the main report.",
        )
        self.discord_output.configure(state="disabled")
        self._style_text_widgets(self.output, self.discord_output)
        self._install_hover_tips()
        self.load_settings()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _setup_help_menu(self):
        mb = tk.Menu(self.root)
        self.root.config(menu=mb)
        m_help = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Help", menu=m_help)
        m_help.add_command(label="Quick guide…", command=self._show_quick_guide)
        m_help.add_separator()
        m_help.add_command(
            label="About hover tips",
            command=lambda: messagebox.showinfo(
                "Hover tips",
                "Rest the mouse on a field or button for about half a second to see a "
                "short explanation. Move the pointer away to dismiss it.",
            ),
        )

    def _show_quick_guide(self):
        win = tk.Toplevel(self.root)
        win.title("Port Battle Planner — Quick guide")
        win.minsize(520, 420)
        win.geometry("700x560")
        tb = self._theme
        win.configure(bg=tb["panel"])
        txt = scrolledtext.ScrolledText(
            win,
            wrap="word",
            font=("Segoe UI", 10),
            padx=12,
            pady=12,
            height=22,
            width=78,
            bg=tb["text_bg"],
            fg=tb["text_fg"],
            insertbackground=tb["text_fg"],
            highlightthickness=2,
            highlightbackground=tb["text_border"],
            highlightcolor=tb["text_border_focus"],
        )
        txt.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        txt.insert("1.0", quick_guide_text())
        txt.configure(state="disabled")
        bf = ttk.Frame(win)
        bf.pack(pady=(0, 10))
        ttk.Button(bf, text="Close", command=win.destroy).pack()

    def _install_hover_tips(self):
        app = self
        HoverTip(
            self.lf_top,
            "Left: how many days to generate and each guild's daily attack window (HH:MM-HH:MM, GMT-6). "
            "Right: comma-separated ports each guild owns — used as labels in the report.",
            app,
            delay_ms=550,
        )
        HoverTip(
            self.days_entry,
            "How many days of schedule to generate from today (GMT-6), including transition logic.",
            app,
        )
        HoverTip(
            self.top_right,
            "Ownership lists: type port names separated by commas. These labels appear in the generated report.",
            app,
            delay_ms=600,
        )
        for guild in GUILDS:
            HoverTip(
                self._ownership_entries[guild],
                f"Ports {guild} is considered to own this week. Separate multiple ports with commas.",
                app,
            )
        HoverTip(
            self.lf_trans,
            "Tell the planner each port's protection state so it can line up timers and windows.",
            app,
            delay_ms=550,
        )
        HoverTip(
            self._lbl_trans_port,
            "Which port this row describes. Must match the built-in port database.",
            app,
        )
        HoverTip(
            self._lbl_trans_state,
            "remaining = protection left; available = can place now; "
            "available_in = cooldown until you may place again.",
            app,
        )
        HoverTip(
            self._lbl_trans_time,
            "Depends on state: duration like 1d 4h, or 'now', or a wait like 9h 30m until available.",
            app,
        )
        HoverTip(
            self.btn_trans_add,
            "Adds another blank row at the bottom of the transition table.",
            app,
        )
        HoverTip(
            self.btn_trans_remove,
            "Deletes the last transition row (useful if you added one by mistake).",
            app,
        )
        HoverTip(
            self.btn_trans_refresh,
            "Reloads port names from the embedded database after you update the script's port list.",
            app,
        )
        HoverTip(
            self.legend_frame,
            "Short definitions of each transition state. Match these to your in-game situation.",
            app,
        )
        HoverTip(
            self.btn_generate,
            "Builds the full schedule and Discord block from windows, ownership, and all transition rows.",
            app,
        )
        HoverTip(
            self.btn_copy_report,
            "Copies the left Output pane (full report) to the clipboard.",
            app,
        )
        HoverTip(
            self.btn_copy_discord,
            "Copies the right pane: weekday grouping and Discord <t:…:F> timestamps for announcements.",
            app,
        )
        HoverTip(
            self.out_lf,
            "Full text report: timers, windows, and checklist. Read-only; use Copy output to grab it.",
            app,
            delay_ms=600,
        )
        HoverTip(
            self.disc_lf,
            "Discord-friendly snippet with bold weekday headers and timestamp tags. "
            "Generated together with the main report.",
            app,
            delay_ms=600,
        )

    def _bind_transition_row_tips(self, rec):
        app = self
        HoverTip(
            rec["port_cb"],
            "Pick the port for this row. Dropdown matches the app's port database.",
            app,
        )
        HoverTip(
            rec["state_cb"],
            "How this port is positioned in its protection / cooldown cycle this week.",
            app,
        )
        HoverTip(
            rec["value_ent"],
            "Time text for the chosen state (e.g. 2d 15h, now, 9h 30m). Same formats the generator expects.",
            app,
        )

    def _try_load_banner(self):
        """
        Optional header image next to the script or exe (or under assets/).

        Tries banner.* then theme_banner.* with extensions
        .png, .gif, .jpg, .jpeg, .webp (same folder, then assets/).

        PNG/GIF use Tk natively; JPEG/WebP need Pillow (pip install pillow).
        Images are scaled to fit while keeping aspect ratio.
        """
        tb = self._theme
        base = _app_base_dir()
        stems = ("banner", "theme_banner")
        exts = (".png", ".gif", ".jpg", ".jpeg", ".webp")
        names = [f"{stem}{ext}" for stem in stems for ext in exts]
        candidates = []
        for fname in names:
            candidates.append(os.path.join(base, fname))
            candidates.append(os.path.join(base, "assets", fname))

        for path in candidates:
            if not os.path.isfile(path):
                continue
            photo = self._load_banner_photo(path)
            if photo is None:
                continue
            self._banner_photo_ref = photo
            bar = tk.Frame(self.root, bg=tb["root"], highlightthickness=0)
            bar.pack(fill="x", side="top")
            lbl = tk.Label(bar, image=photo, bg=tb["root"])
            lbl.pack(pady=(6, 4), anchor="center")
            return

    def _load_banner_pillow(self, path, max_w, max_h):
        """Open raster formats Pillow supports (JPEG, WebP, BMP, etc.)."""
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return None
        try:
            pil = Image.open(path)
        except OSError:
            return None
        if pil.mode not in ("RGB", "RGBA"):
            pil = pil.convert("RGB")
        w, h = pil.size
        scale = min(max_w / max(w, 1), max_h / max(h, 1), 1.0)
        if scale < 1.0:
            nw = max(1, int(w * scale))
            nh = max(1, int(h * scale))
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            pil = pil.resize((nw, nh), resample)
        return ImageTk.PhotoImage(pil)

    def _load_banner_photo(self, path):
        """Return a PhotoImage, or None if the file cannot be loaded."""
        max_w, max_h = 720, 420
        ext = os.path.splitext(path)[1].lower()
        if ext in (".png", ".gif"):
            try:
                img = tk.PhotoImage(file=path)
            except tk.TclError:
                return None
            while img.width() > max_w or img.height() > max_h:
                if img.width() <= 2 or img.height() <= 2:
                    break
                img = img.subsample(2, 2)
            return img
        if ext in (".jpg", ".jpeg", ".webp", ".bmp"):
            return self._load_banner_pillow(path, max_w, max_h)
        return None

    def _style_text_widgets(self, *widgets):
        tb = self._theme
        for w in widgets:
            w.configure(
                bg=tb["text_bg"],
                fg=tb["text_fg"],
                insertbackground=tb["text_fg"],
                selectbackground=tb["select_bg"],
                selectforeground=tb["select_fg"],
                highlightthickness=2,
                highlightbackground=tb["text_border"],
                highlightcolor=tb["text_border_focus"],
            )
        self._setup_report_text_tags()

    def _setup_report_text_tags(self):
        """Syntax-style highlighting for Output / Discord panes (copy still plain text).

        Avoid Consolas *bold* on Windows: Tk often substitutes another face and metrics
        break (overlapping / clipped text). Use color, size, and underline instead.
        """
        tb = self._theme
        mono = "Consolas"
        body = (mono, 12)
        for w in (self.output, self.discord_output):
            w.tag_configure(
                "out_h1",
                foreground=tb["title"],
                font=(mono, 12),
                underline=True,
                spacing3=8,
            )
            w.tag_configure(
                "out_rule",
                foreground=tb["muted"],
                font=(mono, 11),
                spacing3=6,
            )
            w.tag_configure(
                "out_day",
                foreground=tb["accent"],
                font=(mono, 12),
                spacing1=6,
                spacing3=2,
            )
            w.tag_configure("out_line", foreground=tb["text_fg"], font=body)
            w.tag_configure("out_dim", foreground=tb["muted"], font=(mono, 11))
            w.tag_configure("out_indent", lmargin1=20, lmargin2=20)
            w.tag_configure("out_step", foreground=tb["title"], font=(mono, 12))
            w.tag_configure("out_port", foreground=tb["accent"], font=body)
            w.tag_configure("out_note", foreground=tb["muted"], font=(mono, 11))

    def _insert_tagged_report(self, widget, text, *, discord=False):
        """Insert line by line; apply tags via tag_add (never pass tag names into insert).

        ScrolledText/Text: index(tk.END) before insert is often '2.0' while the first line of
        text is inserted at 1.x, so start+len(line) chars never advances — tags attach to an
        empty range. After each insert(END, line), use end-1c linestart .. end-1c instead.
        """
        self._setup_report_text_tags()
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        for line in text.splitlines():
            tags = report_output_line_tags(line, discord=discord)
            if isinstance(tags, str):
                tags = (tags,)
            if line:
                widget.insert(tk.END, line)
                start = widget.index("end-1c linestart")
                end_excl = widget.index("end-1c")
                if tags:
                    for tname in tags:
                        widget.tag_add(tname, start, end_excl)
            widget.insert(tk.END, "\n")
        widget.configure(state="disabled")

    def _configure_styles(self):
        # Black chrome; gold for titles/headers; crimson for borders, buttons, and selection.
        self._theme = {
            "root": "#000000",
            "panel": "#0a0a0a",
            "input": "#141414",
            "fg": "#ededed",
            "muted": "#9a9a9a",
            "hint": "#555555",
            "title": "#e6bc2f",
            "accent": "#d4a017",
            "accent_dim": "#3a1215",
            "border": "#6a2228",
            "input_border": "#3d3d3d",
            "input_border_focus": "#6e6e6e",
            "text_bg": "#000000",
            "text_fg": "#e8e8e8",
            "select_bg": "#6e181c",
            "select_fg": "#ffffff",
            # Visible against black text_bg; focus ring steps up clearly.
            "text_border": "#404040",
            "text_border_focus": "#7a7a7a",
        }
        t = self._theme

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        ui = ("Segoe UI", 10)
        style.configure(".", background=t["panel"], foreground=t["fg"])
        style.configure("TFrame", background=t["panel"])
        style.configure("TLabel", background=t["panel"], foreground=t["fg"], font=ui)
        style.configure(
            "TLabelframe",
            background=t["panel"],
            foreground=t["fg"],
            bordercolor=t["border"],
            relief="solid",
            borderwidth=1,
        )
        style.configure(
            "TLabelframe.Label",
            background=t["panel"],
            foreground=t["title"],
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "Title.TLabel",
            font=("Segoe UI", 18, "bold"),
            background=t["panel"],
            foreground=t["title"],
        )
        style.configure(
            "Subheader.TLabel",
            font=("Segoe UI", 11, "bold"),
            background=t["panel"],
            foreground=t["title"],
        )
        style.configure(
            "TableHeader.TLabel",
            font=("Segoe UI", 10, "bold"),
            background=t["panel"],
            foreground=t["accent"],
        )
        style.configure(
            "Muted.TLabel",
            font=("Segoe UI", 9),
            background=t["panel"],
            foreground=t["muted"],
        )
        style.configure(
            "Hint.TLabel",
            font=("Segoe UI", 9),
            background=t["panel"],
            foreground=t["hint"],
        )
        entry_font = ("Segoe UI", 11)
        style.configure(
            "TEntry",
            fieldbackground=t["input"],
            foreground=t["fg"],
            insertcolor=t["fg"],
            bordercolor=t["input_border"],
            lightcolor=t["input"],
            darkcolor=t["input_border"],
            font=entry_font,
            padding=(4, 3),
        )
        style.map(
            "TEntry",
            bordercolor=[
                ("focus", t["input_border_focus"]),
                ("!focus", t["input_border"]),
            ],
            lightcolor=[("focus", t["input"]), ("!focus", t["input"])],
            darkcolor=[
                ("focus", t["input_border_focus"]),
                ("!focus", t["input_border"]),
            ],
        )
        style.configure(
            "TCombobox",
            fieldbackground=t["input"],
            background=t["input"],
            foreground=t["fg"],
            arrowcolor=t["title"],
            bordercolor=t["input_border"],
            lightcolor=t["input"],
            darkcolor=t["input_border"],
            font=entry_font,
            padding=(4, 3),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", t["input"]), ("disabled", t["panel"])],
            selectbackground=[("readonly", t["accent_dim"])],
            selectforeground=[("readonly", t["select_fg"])],
            bordercolor=[
                ("focus", t["input_border_focus"]),
                ("!focus", t["input_border"]),
                ("readonly", t["input_border"]),
            ],
            darkcolor=[
                ("focus", t["input_border_focus"]),
                ("!focus", t["input_border"]),
                ("readonly", t["input_border"]),
            ],
        )
        style.configure(
            "TButton",
            font=ui,
            padding=(12, 6),
            background=t["accent_dim"],
            foreground=t["fg"],
            bordercolor=t["border"],
            focuscolor=t["title"],
        )
        style.map(
            "TButton",
            background=[
                ("active", "#b8920f"),
                ("pressed", t["accent_dim"]),
            ],
            foreground=[("disabled", t["muted"])],
        )

    def _port_names_from_db(self):
        try:
            ports = get_port_database()
            return [p["name"] for p in sorted(ports, key=lambda x: x["name"].lower())]
        except Exception:
            return []

    def _transition_append_row_ui(self, port, state, value):
        names = self._port_names_from_db()
        if state not in TRANSITION_STATES:
            state = "remaining"
        row = 1 + len(self.transition_row_widgets)
        port_var = tk.StringVar(value=port if port in names else "")
        state_var = tk.StringVar(value=state)
        value_var = tk.StringVar(value=value)

        cb_port = ttk.Combobox(
            self.transition_form,
            textvariable=port_var,
            values=names,
            width=26,
            state="readonly",
        )
        cb_port.grid(row=row, column=0, sticky="ew", padx=(0, 8), pady=3)
        if port and port in names:
            port_var.set(port)

        cb_state = ttk.Combobox(
            self.transition_form,
            textvariable=state_var,
            values=TRANSITION_STATES,
            width=14,
            state="readonly",
        )
        cb_state.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=3)

        ent_val = ttk.Entry(self.transition_form, textvariable=value_var, width=22)
        ent_val.grid(row=row, column=2, sticky="ew", pady=3)

        rec = {
            "row": row,
            "port_var": port_var,
            "state_var": state_var,
            "value_var": value_var,
            "port_cb": cb_port,
            "state_cb": cb_state,
            "value_ent": ent_val,
        }
        self.transition_row_widgets.append(rec)
        self._bind_transition_row_tips(rec)

    def _rebuild_transition_rows(self, rows):
        for rec in list(self.transition_row_widgets):
            rec["port_cb"].destroy()
            rec["state_cb"].destroy()
            rec["value_ent"].destroy()
        self.transition_row_widgets.clear()
        for row in rows:
            self._transition_append_row_ui(
                row.get("port", "").strip(),
                row.get("state", "remaining").strip().lower(),
                row.get("value", "").strip(),
            )
        if not self.transition_row_widgets:
            self._transition_append_row_ui("", "remaining", "")

    def _transition_add_row(self):
        self._transition_append_row_ui("", "remaining", "")

    def _transition_remove_row(self):
        if len(self.transition_row_widgets) <= 1:
            return
        rec = self.transition_row_widgets.pop()
        rec["port_cb"].destroy()
        rec["state_cb"].destroy()
        rec["value_ent"].destroy()

    def _transition_refresh_ports(self):
        names = self._port_names_from_db()
        for rec in self.transition_row_widgets:
            rec["port_cb"]["values"] = names
            cur = rec["port_var"].get().strip()
            if cur and cur not in names:
                rec["port_var"].set("")

    def collect_transition_text(self):
        lines = []
        for rec in self.transition_row_widgets:
            port = rec["port_var"].get().strip()
            if not port:
                continue
            state = rec["state_var"].get().strip().lower()
            if state not in TRANSITION_STATES:
                raise ValueError(f"Invalid state for port {port}.")
            value = rec["value_var"].get().strip()
            if state in ("remaining", "available_in") and not value:
                raise ValueError(f"{port}: enter a time value (e.g. 9h 30m or 1d 4h).")
            if state == "available" and not value:
                value = "now"
            lines.append(f"{port},{state},{value}")
        return "\n".join(lines)

    def transition_rows_for_save(self):
        rows = []
        for rec in self.transition_row_widgets:
            rows.append(
                {
                    "port": rec["port_var"].get().strip(),
                    "state": rec["state_var"].get().strip().lower(),
                    "value": rec["value_var"].get().strip(),
                }
            )
        return rows

    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return

        self.days_var.set(str(data.get("days", self.days_var.get())))
        for guild in GUILDS:
            if "windows" in data and guild in data["windows"]:
                self.window_vars[guild].set(data["windows"][guild])
            if "ownership" in data and guild in data["ownership"]:
                self.ownership_vars[guild].set(data["ownership"][guild])

        if "transition_rows" in data and isinstance(data["transition_rows"], list):
            self._rebuild_transition_rows(data["transition_rows"])
        elif "transition_data" in data and isinstance(data["transition_data"], str):
            parsed = []
            for raw_line in data["transition_data"].splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) == 3:
                    parsed.append(
                        {"port": parts[0], "state": parts[1].lower(), "value": parts[2]}
                    )
            if parsed:
                self._rebuild_transition_rows(parsed)
        self._transition_refresh_ports()

    def save_settings(self):
        data = {
            "days": self.days_var.get().strip(),
            "windows": {guild: self.window_vars[guild].get() for guild in GUILDS},
            "ownership": {guild: self.ownership_vars[guild].get() for guild in GUILDS},
            "transition_rows": self.transition_rows_for_save(),
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    def generate_output(self):
        try:
            days = int(self.days_var.get().strip())
            if days < 1 or days > 31:
                raise ValueError("Days must be between 1 and 31.")

            guild_windows = {}
            for guild in GUILDS:
                guild_windows[guild] = parse_window(self.window_vars[guild].get())

            port_database = get_port_database()
            ownership_inputs = {guild: self.ownership_vars[guild].get() for guild in GUILDS}
            port_owners = parse_ownership(ownership_inputs, port_database)
            transition_states = parse_transition_state(
                self.collect_transition_text(), port_database
            )

            now_dt = datetime.now(GMT_MINUS_6)
            report = create_report(
                days, guild_windows, port_database, port_owners, transition_states, now_dt
            )
            transition_report = create_transition_report(
                now_dt,
                transition_states,
                port_database,
                port_owners,
                guild_windows,
            )
            report = report + "\n\n" + transition_report
            discord_snippet = create_discord_battle_snippet(
                days, guild_windows, port_database, port_owners, transition_states, now_dt
            )
            self.save_settings()
        except Exception as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        self._setup_report_text_tags()
        self._insert_tagged_report(self.output, report, discord=False)
        self._insert_tagged_report(self.discord_output, discord_snippet, discord=True)

    def copy_output(self):
        text_value = self.output.get("1.0", tk.END).strip()
        if not text_value:
            messagebox.showinfo("Copy Output", "Nothing to copy.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text_value)
        messagebox.showinfo("Copy Output", "Report copied to clipboard.")

    def copy_discord_output(self):
        text_value = self.discord_output.get("1.0", tk.END).strip()
        if not text_value:
            messagebox.showinfo("Copy Discord", "Nothing to copy.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text_value)
        messagebox.showinfo("Copy Discord", "Discord announcement copied to clipboard.")

    def on_close(self):
        try:
            self.save_settings()
        except Exception:
            pass
        self.root.destroy()


def main():
    _windows_set_per_monitor_dpi_aware()
    root = tk.Tk()
    PortPlannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
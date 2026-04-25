"""Live Discord voice-state tracker via Gateway (voice events)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import websockets

from app.config import Settings

_INTENT_GUILDS = 1 << 0
_INTENT_GUILD_VOICE_STATES = 1 << 7
_INTENT_GUILD_MEMBERS = 1 << 1
_IDENTIFY_INTENTS = _INTENT_GUILDS | _INTENT_GUILD_VOICE_STATES | _INTENT_GUILD_MEMBERS


class DiscordVoiceTracker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._voice_by_user: dict[str, str] = {}
        self._last_error: str = ""
        self._last_event_at: float = 0.0

    async def start(self, settings: Settings) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        if not settings.discord_bot_token or not settings.discord_guild_id:
            self._last_error = "Discord bot token or guild id missing."
            return
        self._task = asyncio.create_task(self._run_forever(settings))

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None

    async def snapshot(self) -> dict[str, str]:
        async with self._lock:
            return dict(self._voice_by_user)

    async def stats(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "connected_count": len(self._voice_by_user),
                "last_event_at": self._last_event_at,
                "last_error": self._last_error,
                "running": bool(self._task and not self._task.done()),
            }

    async def _run_forever(self, settings: Settings) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._run_once(settings)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                async with self._lock:
                    self._last_error = f"{type(exc).__name__}: {exc}"
                await asyncio.sleep(backoff)
                backoff = min(30.0, backoff * 1.8)

    async def _gateway_url(self, settings: Settings) -> str:
        headers = {"Authorization": f"Bot {settings.discord_bot_token}"}
        async with httpx.AsyncClient() as client:
            r = await client.get("https://discord.com/api/v10/gateway/bot", headers=headers, timeout=20.0)
            r.raise_for_status()
            data = r.json()
        base = str(data.get("url") or "wss://gateway.discord.gg")
        return f"{base}?v=10&encoding=json"

    async def _run_once(self, settings: Settings) -> None:
        url = await self._gateway_url(settings)
        heartbeat_ack = True
        seq: int | None = None

        async with websockets.connect(url, max_size=2**22) as ws:
            hello = json.loads(await ws.recv())
            interval_ms = int((hello.get("d") or {}).get("heartbeat_interval") or 45000)

            async def heartbeat_loop() -> None:
                nonlocal heartbeat_ack, seq
                while not self._stop.is_set():
                    await asyncio.sleep(interval_ms / 1000.0)
                    if not heartbeat_ack:
                        raise RuntimeError("Discord heartbeat not acknowledged")
                    heartbeat_ack = False
                    await ws.send(json.dumps({"op": 1, "d": seq}))

            hb_task = asyncio.create_task(heartbeat_loop())
            try:
                identify = {
                    "op": 2,
                    "d": {
                        "token": settings.discord_bot_token,
                        "intents": _IDENTIFY_INTENTS,
                        "properties": {"os": "windows", "browser": "wosb-site", "device": "wosb-site"},
                    },
                }
                await ws.send(json.dumps(identify))

                while not self._stop.is_set():
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    op = int(msg.get("op", -1))
                    t = msg.get("t")
                    d = msg.get("d")
                    if msg.get("s") is not None:
                        seq = int(msg.get("s"))

                    if op == 11:
                        heartbeat_ack = True
                        continue
                    if op in (7, 9):
                        raise RuntimeError(f"Gateway requested reconnect (op={op})")

                    if t == "GUILD_CREATE" and isinstance(d, dict):
                        gid = str(d.get("id") or "")
                        if gid != str(settings.discord_guild_id):
                            continue
                        voice_states = d.get("voice_states") if isinstance(d.get("voice_states"), list) else []
                        async with self._lock:
                            self._voice_by_user = {}
                            for vs in voice_states:
                                if not isinstance(vs, dict):
                                    continue
                                uid = str(vs.get("user_id") or "").strip()
                                ch = str(vs.get("channel_id") or "").strip()
                                if uid and ch:
                                    self._voice_by_user[uid] = ch
                            self._last_event_at = time.time()
                            self._last_error = ""
                        continue

                    if t == "VOICE_STATE_UPDATE" and isinstance(d, dict):
                        gid = str(d.get("guild_id") or "")
                        if gid and gid != str(settings.discord_guild_id):
                            continue
                        uid = str(d.get("user_id") or "").strip()
                        if not uid:
                            continue
                        ch = str(d.get("channel_id") or "").strip()
                        async with self._lock:
                            if ch:
                                self._voice_by_user[uid] = ch
                            else:
                                self._voice_by_user.pop(uid, None)
                            self._last_event_at = time.time()
                            self._last_error = ""
            finally:
                hb_task.cancel()
                try:
                    await hb_task
                except Exception:
                    pass


_TRACKER = DiscordVoiceTracker()


async def start_voice_tracker(settings: Settings) -> None:
    await _TRACKER.start(settings)


async def stop_voice_tracker() -> None:
    await _TRACKER.stop()


async def get_voice_snapshot() -> dict[str, str]:
    return await _TRACKER.snapshot()


async def get_voice_tracker_stats() -> dict[str, Any]:
    return await _TRACKER.stats()


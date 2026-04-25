"""Cache-busting version for static assets (mtime of main CSS + roster board CSS)."""

from pathlib import Path

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def static_asset_version() -> str:
    mt = 0.0
    for name in ("style.css", "rosters-board.css"):
        p = _STATIC_DIR / name
        try:
            mt = max(mt, p.stat().st_mtime)
        except OSError:
            continue
    return str(int(mt)) if mt else "1"

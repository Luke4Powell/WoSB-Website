import re
import uuid
from pathlib import Path

from fastapi import UploadFile

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_ALLOWED_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})


def reimbursement_upload_dir(base_dir: Path) -> Path:
    return base_dir / "data" / "reimbursement_uploads"


def _safe_suffix(filename: str) -> str:
    lower = (filename or "").lower().strip()
    for suf in _ALLOWED_SUFFIXES:
        if lower.endswith(suf):
            return suf
    return ""


def validate_image_upload(upload: UploadFile) -> str:
    """Return normalized file suffix (e.g. '.png') or raise ValueError."""
    name = upload.filename or ""
    suf = _safe_suffix(name)
    if not suf:
        raise ValueError("Screenshot must be an image (PNG, JPG, JPEG, WebP, or GIF).")
    return suf


async def save_reimbursement_image(
    *,
    base_dir: Path,
    request_id: int,
    role: str,
    upload: UploadFile,
) -> str:
    """Persist upload under data/reimbursement_uploads; returns stored relative filename."""
    suffix = validate_image_upload(upload)
    body = await upload.read()
    if len(body) > MAX_UPLOAD_BYTES:
        raise ValueError("Image is too large (max 5 MB).")
    if len(body) == 0:
        raise ValueError("Empty file.")

    out_dir = reimbursement_upload_dir(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    # Filename on disk (no path traversal)
    safe_role = re.sub(r"[^a-z]+", "", role.lower())[:12] or "img"
    fname = f"{request_id}_{safe_role}_{token}{suffix}"
    dest = out_dir / fname
    dest.write_bytes(body)
    return fname

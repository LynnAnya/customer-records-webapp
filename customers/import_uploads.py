"""Keeps an uploaded Excel file between "check" and "confirm" on the import page.

The file holds real customer data, so it lives only in a private temporary
folder on the server, for at most MAX_AGE, and is deleted after the import.
The browser never sends a file name or path back: the session holds a random
token, so one admin can only ever reach their own upload.
"""

import os
import re
import secrets
import tempfile
import time
from pathlib import Path

from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest

UPLOAD_DIR = Path(tempfile.gettempdir()) / "customer-imports"
MAX_AGE_SECONDS = 30 * 60
SESSION_KEY = "excel_import"
TOKEN = re.compile(r"[0-9a-f]{32}")


def _path(token: str) -> Path:
    return UPLOAD_DIR / f"{token}.xlsx"


def remove_stale_uploads() -> None:
    """Delete every upload older than MAX_AGE (from any admin)."""
    if not UPLOAD_DIR.is_dir():
        return
    cutoff = time.time() - MAX_AGE_SECONDS
    for path in UPLOAD_DIR.glob("*.xlsx"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except FileNotFoundError:
            pass  # removed by another request at the same moment


def save_upload(request: HttpRequest, upload: UploadedFile) -> None:
    """Store the file for this admin, replacing their previous upload."""
    remove_stale_uploads()
    discard_upload(request)
    UPLOAD_DIR.mkdir(mode=0o700, exist_ok=True)
    token = secrets.token_hex(16)
    # Created readable by this server process only.
    descriptor = os.open(_path(token), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        for chunk in upload.chunks():
            target.write(chunk)
    request.session[SESSION_KEY] = {"token": token, "name": upload.name[:120]}


def current_upload(request: HttpRequest) -> tuple[Path, str] | None:
    """This admin's stored file and its original name, if still there."""
    info = request.session.get(SESSION_KEY) or {}
    token = str(info.get("token", ""))
    if not TOKEN.fullmatch(token):
        return None
    path = _path(token)
    try:
        fresh = time.time() - path.stat().st_mtime < MAX_AGE_SECONDS
    except FileNotFoundError:
        return None
    if not fresh:
        discard_upload(request)
        return None
    return path, str(info.get("name", ""))


def discard_upload(request: HttpRequest) -> None:
    info = request.session.pop(SESSION_KEY, None) or {}
    token = str(info.get("token", ""))
    if TOKEN.fullmatch(token):
        _path(token).unlink(missing_ok=True)

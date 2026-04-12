"""Small helpers used across blueprints."""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import current_app
from werkzeug.utils import secure_filename

# Eastern time zone — used throughout the app for all timestamps.
EASTERN = ZoneInfo("America/New_York")


def now_eastern() -> datetime:
    """Return current time in US/Eastern as a naive datetime.

    Stored as naive in SQLite but represents Eastern time, not UTC.
    Automatically handles EST/EDT transitions.
    """
    return datetime.now(EASTERN).replace(tzinfo=None)


def allowed_upload(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in current_app.config["ALLOWED_UPLOAD_EXTENSIONS"]


def make_stored_filename(original: str) -> str:
    safe = secure_filename(original) or "file"
    return f"{uuid.uuid4().hex}_{safe}"


def upload_path(stored_name: str) -> Path:
    return Path(current_app.config["UPLOAD_FOLDER"]) / stored_name


def save_upload(file_storage) -> tuple[str, int]:
    """Save an uploaded file and return (stored_filename, size_bytes)."""
    stored = make_stored_filename(file_storage.filename)
    dest = upload_path(stored)
    dest.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(dest)
    size = os.path.getsize(dest)
    return stored, size

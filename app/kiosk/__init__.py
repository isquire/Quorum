"""Kiosk check-in blueprint for observed self-service attendance."""
from __future__ import annotations

from flask import Blueprint, current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

bp = Blueprint("kiosk", __name__, url_prefix="/kiosk")

KIOSK_SALT = "kiosk-checkin"
KIOSK_MAX_AGE = 43200  # 12 hours in seconds


def generate_kiosk_token(meeting_id: int) -> str:
    """Create a signed token granting kiosk check-in access to one meeting."""
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return s.dumps({"meeting_id": meeting_id}, salt=KIOSK_SALT)


def validate_kiosk_token(token: str) -> int | None:
    """Return meeting_id if token is valid, else None."""
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        data = s.loads(token, salt=KIOSK_SALT, max_age=KIOSK_MAX_AGE)
        return data.get("meeting_id")
    except (BadSignature, SignatureExpired):
        return None


from . import routes  # noqa: E402, F401

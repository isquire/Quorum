"""Helper for recording admin audit-log entries."""
from __future__ import annotations

from .extensions import db
from .models import AdminAction
from .utils import now_eastern


def log_admin_action(
    admin_id: int,
    action: str,
    target_type: str,
    target_id: int | None,
    detail: str,
) -> AdminAction:
    """Create an AdminAction record.  Caller must commit the session."""
    entry = AdminAction(
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        created_at=now_eastern(),
    )
    db.session.add(entry)
    return entry

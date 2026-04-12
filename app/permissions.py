"""Role-based access control decorators."""
from __future__ import annotations

from functools import wraps

from flask import abort
from flask_login import current_user

from .models import Role

# Roles that carry chair-equivalent privileges (drive meetings, advance
# stages, open/close votes).  Used both by decorators and template guards.
CHAIR_ROLES: set[str] = {
    Role.admin.value,
    Role.chair.value,
    Role.vice_chair.value,
    Role.pastor.value,
}

# Roles that can take secretary actions (roll call, notes, edit minutes).
SECRETARY_ROLES: set[str] = CHAIR_ROLES | {Role.secretary.value}


def role_required(*roles: Role | str):
    """Abort 403 unless the current user has one of the given roles.

    Admin always passes.
    """
    wanted = {r.value if isinstance(r, Role) else r for r in roles}

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role == Role.admin:
                return view(*args, **kwargs)
            if current_user.role.value not in wanted:
                abort(403)
            return view(*args, **kwargs)

        return wrapper

    return decorator


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if current_user.role != Role.admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def voting_member_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_voting_member:
            abort(403)
        return view(*args, **kwargs)

    return wrapper

"""Kiosk check-in routes — token-authenticated, no login required."""
from __future__ import annotations

from flask import abort, render_template, request

from ..extensions import db
from ..models import Meeting, MeetingAttendance, MeetingStatus, User
from ..utils import now_eastern
from .. import minutes_logger
from . import bp, validate_kiosk_token


def _load_meeting_from_token(token: str) -> Meeting:
    """Validate token and return the meeting, or 404."""
    meeting_id = validate_kiosk_token(token)
    if meeting_id is None:
        abort(404)
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.status == MeetingStatus.cancelled:
        abort(404)
    return meeting


@bp.route("/<token>")
def checkin_page(token: str):
    """Main kiosk check-in page — no login required."""
    meeting = _load_meeting_from_token(token)
    attendees = _get_attendees(meeting)
    return render_template(
        "kiosk/checkin.html",
        meeting=meeting,
        token=token,
        attendees=attendees,
    )


@bp.route("/<token>/checkin/<int:user_id>", methods=["POST"])
def checkin(token: str, user_id: int):
    """Mark a user as present via kiosk — returns HTMX partial."""
    meeting = _load_meeting_from_token(token)

    attendance = MeetingAttendance.query.filter_by(
        meeting_id=meeting.id, user_id=user_id
    ).first_or_404()
    user = User.query.get_or_404(user_id)

    checked_in_name = None
    if not attendance.is_present:
        attendance.is_present = True
        if attendance.arrived_at is None:
            attendance.arrived_at = now_eastern()
        minutes_logger.log_kiosk_checkin(meeting, user)
        db.session.commit()
        checked_in_name = user.full_name

    # Return the updated attendee list partial.
    q = request.args.get("q", "").strip()
    letter = request.args.get("letter", "").strip()
    attendees = _get_attendees(meeting, q=q, letter=letter)
    return render_template(
        "kiosk/_attendees.html",
        meeting=meeting,
        token=token,
        attendees=attendees,
        checked_in_name=checked_in_name,
    )


@bp.route("/<token>/fragment/quorum")
def fragment_quorum(token: str):
    """HTMX partial — quorum badge for kiosk view."""
    meeting = _load_meeting_from_token(token)
    return render_template("kiosk/_quorum.html", meeting=meeting, token=token)


@bp.route("/<token>/fragment/attendees")
def fragment_attendees(token: str):
    """HTMX partial — filtered attendee list for kiosk view."""
    meeting = _load_meeting_from_token(token)
    q = request.args.get("q", "").strip()
    letter = request.args.get("letter", "").strip()
    attendees = _get_attendees(meeting, q=q, letter=letter)
    return render_template(
        "kiosk/_attendees.html",
        meeting=meeting,
        token=token,
        attendees=attendees,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_attendees(
    meeting: Meeting, q: str = "", letter: str = ""
) -> list[MeetingAttendance]:
    """Return meeting attendances filtered by search query or letter.

    Not-yet-present attendees sort first (alphabetically),
    already-present attendees sort after.
    """
    attendances = list(meeting.attendances)

    if q:
        q_lower = q.lower()
        attendances = [
            a for a in attendances
            if a.user is not None and q_lower in a.user.full_name.lower()
        ]
    elif letter:
        letter_upper = letter.upper()
        attendances = [
            a for a in attendances
            if a.user is not None
            and a.user.full_name.upper().startswith(letter_upper)
        ]

    # Sort: not-present first (alphabetically), then present (alphabetically).
    attendances.sort(
        key=lambda a: (
            a.is_present,
            (a.user.full_name if a.user else ""),
        )
    )
    return attendances

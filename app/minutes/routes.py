from flask import Response, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Meeting, MeetingStatus, Role
from ..permissions import SECRETARY_ROLES, role_required
from ..utils import now_eastern
from . import bp


@bp.route("/")
@login_required
def list_minutes():
    meetings = (
        Meeting.query.filter(
            Meeting.status.in_(
                [MeetingStatus.adjourned, MeetingStatus.in_progress]
            ),
            Meeting.is_archived == False,  # noqa: E712
        )
        .order_by(Meeting.scheduled_start.desc())
        .all()
    )
    return render_template("minutes/list.html", meetings=meetings)


@bp.route("/<int:meeting_id>")
@login_required
def detail(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    return render_template(
        "minutes/detail.html",
        meeting=meeting,
        secretary_roles=SECRETARY_ROLES,
    )


@bp.route("/<int:meeting_id>/approve", methods=["POST"])
@role_required(Role.chair, Role.vice_chair)
def approve(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    meeting.minutes_approved_at = now_eastern()
    meeting.minutes_approved_by_id = current_user.id
    db.session.commit()
    flash("Minutes approved.", "success")
    return redirect(url_for("minutes.detail", meeting_id=meeting_id))


@bp.route("/<int:meeting_id>/export.txt")
@login_required
def export_text(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    lines = [
        f"MINUTES — {meeting.title}",
        f"Date: {meeting.scheduled_start.strftime('%Y-%m-%d %I:%M %p')} ET",
        f"Type: {meeting.meeting_type.value}",
        f"Location: {meeting.location or 'N/A'}",
        "",
        "Attendance:",
    ]
    for a in meeting.attendances:
        status = "present" if a.is_present else "absent"
        lines.append(f"  - {a.user.full_name} ({status})")
    can_view_confidential = current_user.role.value in SECRETARY_ROLES
    has_confidential = any(e.is_confidential for e in meeting.minutes_entries)

    if has_confidential and not can_view_confidential:
        lines.append("")
        lines.append(
            "NOTE: Some proceedings are marked confidential and have been"
        )
        lines.append("redacted from this copy.")

    lines.append("")
    lines.append("Proceedings:")
    for entry in meeting.minutes_entries:
        ts = entry.timestamp.strftime("%H:%M")
        if entry.is_confidential and not can_view_confidential:
            lines.append(f"  [{ts}] [CONFIDENTIAL — content restricted to officers]")
        else:
            lines.append(f"  [{ts}] {entry.text}")
    body = "\n".join(lines) + "\n"
    return Response(
        body,
        mimetype="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="minutes-{meeting.id}.txt"'
        },
    )

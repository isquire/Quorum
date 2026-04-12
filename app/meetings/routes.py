from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import (
    Meeting,
    MeetingAttendance,
    MeetingStage,
    MeetingStatus,
    MeetingType,
    Role,
    RsvpStatus,
    User,
)
from ..permissions import role_required
from . import bp
from .forms import MeetingForm, RsvpForm


def _ensure_attendance_rows(meeting: Meeting) -> None:
    """Ensure every active user has an attendance row for a meeting."""
    existing_user_ids = {a.user_id for a in meeting.attendances}
    users = User.query.filter_by(is_active=True).all()
    for user in users:
        if user.id not in existing_user_ids:
            db.session.add(
                MeetingAttendance(
                    meeting_id=meeting.id,
                    user_id=user.id,
                    rsvp_status=RsvpStatus.no_response,
                    is_present=False,
                )
            )


@bp.route("/")
@login_required
def list_meetings():
    now = datetime.utcnow()
    upcoming = (
        Meeting.query.filter(
            Meeting.status.in_(
                [MeetingStatus.scheduled, MeetingStatus.in_progress]
            )
        )
        .order_by(Meeting.scheduled_start.asc())
        .all()
    )
    past = (
        Meeting.query.filter(
            Meeting.status.in_(
                [MeetingStatus.adjourned, MeetingStatus.cancelled]
            )
        )
        .order_by(Meeting.scheduled_start.desc())
        .limit(50)
        .all()
    )
    return render_template(
        "meetings/list.html", upcoming=upcoming, past=past, now=now
    )


@bp.route("/new", methods=["GET", "POST"])
@role_required(Role.chair, Role.vice_chair)
def create_meeting():
    form = MeetingForm()
    if form.validate_on_submit():
        meeting = Meeting(
            title=form.title.data.strip(),
            meeting_type=MeetingType(form.meeting_type.data),
            scheduled_start=form.scheduled_start.data,
            scheduled_end=form.scheduled_end.data,
            location=(form.location.data or "").strip(),
            status=MeetingStatus.scheduled,
            current_stage=MeetingStage.not_started,
            created_by_id=current_user.id,
        )
        db.session.add(meeting)
        db.session.flush()  # get meeting.id
        _ensure_attendance_rows(meeting)
        db.session.commit()
        flash("Meeting created.", "success")
        return redirect(url_for("meetings.meeting_detail", meeting_id=meeting.id))
    return render_template("meetings/form.html", form=form, action="new")


@bp.route("/<int:meeting_id>")
@login_required
def meeting_detail(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    _ensure_attendance_rows(meeting)
    db.session.commit()

    my_attendance = next(
        (a for a in meeting.attendances if a.user_id == current_user.id),
        None,
    )
    rsvp_form = RsvpForm()
    if my_attendance:
        rsvp_form.rsvp.data = my_attendance.rsvp_status.value

    return render_template(
        "meetings/detail.html",
        meeting=meeting,
        my_attendance=my_attendance,
        rsvp_form=rsvp_form,
    )


@bp.route("/<int:meeting_id>/edit", methods=["GET", "POST"])
@role_required(Role.chair, Role.vice_chair)
def edit_meeting(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.status == MeetingStatus.adjourned:
        abort(403)
    form = MeetingForm(obj=meeting)
    if not form.is_submitted():
        form.meeting_type.data = meeting.meeting_type.value
    if form.validate_on_submit():
        meeting.title = form.title.data.strip()
        meeting.meeting_type = MeetingType(form.meeting_type.data)
        meeting.scheduled_start = form.scheduled_start.data
        meeting.scheduled_end = form.scheduled_end.data
        meeting.location = (form.location.data or "").strip()
        db.session.commit()
        flash("Meeting updated.", "success")
        return redirect(
            url_for("meetings.meeting_detail", meeting_id=meeting.id)
        )
    return render_template(
        "meetings/form.html", form=form, action="edit", meeting=meeting
    )


@bp.route("/<int:meeting_id>/cancel", methods=["POST"])
@role_required(Role.chair, Role.vice_chair)
def cancel_meeting(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    meeting.status = MeetingStatus.cancelled
    db.session.commit()
    flash("Meeting cancelled.", "info")
    return redirect(url_for("meetings.list_meetings"))


@bp.route("/<int:meeting_id>/rsvp", methods=["POST"])
@login_required
def rsvp(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    form = RsvpForm()
    if not form.validate_on_submit():
        flash("Invalid RSVP.", "danger")
        return redirect(url_for("meetings.meeting_detail", meeting_id=meeting_id))

    attendance = next(
        (a for a in meeting.attendances if a.user_id == current_user.id), None
    )
    if attendance is None:
        attendance = MeetingAttendance(
            meeting_id=meeting.id, user_id=current_user.id
        )
        db.session.add(attendance)
    attendance.rsvp_status = RsvpStatus(form.rsvp.data)
    db.session.commit()
    flash("RSVP recorded.", "success")
    return redirect(url_for("meetings.meeting_detail", meeting_id=meeting_id))

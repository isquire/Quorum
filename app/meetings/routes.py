from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..admin_log import log_admin_action
from ..extensions import db
from ..models import (
    AgendaCategory,
    AgendaItem,
    Board,
    BoardMembership,
    Meeting,
    MeetingAttendance,
    MeetingStage,
    MeetingStatus,
    MeetingTemplate,
    MeetingTemplateItem,
    MeetingType,
    Role,
    RsvpStatus,
    User,
)
from ..permissions import SECRETARY_ROLES, admin_required, role_required
from ..utils import now_eastern
from ..kiosk import generate_kiosk_token
from . import bp
from .forms import MeetingForm, RsvpForm


def _populate_board_choices(form: MeetingForm) -> None:
    """Fill board_id choices from the boards table."""
    boards = Board.query.order_by(Board.display_name).all()
    form.board_id.choices = [(b.id, b.display_name) for b in boards]


def _populate_acting_chair_choices(form: MeetingForm) -> None:
    """Fill acting_chair_id choices with eligible users.

    Bylaws Art I §2: the Board of Deacons selects a temporary chair
    from its membership. Any active user who is an officer can be an
    acting chair.
    """
    users = (
        User.query.filter_by(is_active=True)
        .order_by(User.full_name)
        .all()
    )
    form.acting_chair_id.choices = [(0, "— Pastor chairs (default) —")] + [
        (u.id, u.full_name) for u in users
    ]


def _ensure_attendance_rows(meeting: Meeting) -> None:
    """Ensure relevant users have attendance rows for a meeting.

    For board meetings, attendance is limited to board members.
    For assembly meetings (or meetings without a board), all active users.
    """
    existing_user_ids = {a.user_id for a in meeting.attendances}
    if meeting.board and meeting.board.slug != "assembly":
        # Board meeting: attendance is board members only.
        users = [
            m.user for m in meeting.board.memberships
            if m.user is not None and m.user.is_active
        ]
    else:
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
    now = now_eastern()
    show = request.args.get("show", "")

    if show == "archived":
        archived = (
            Meeting.query.filter_by(is_archived=True)
            .order_by(Meeting.scheduled_start.desc())
            .all()
        )
        return render_template(
            "meetings/list.html",
            upcoming=[],
            past=[],
            archived=archived,
            show_archived=True,
            now=now,
        )

    upcoming = (
        Meeting.query.filter(
            Meeting.status.in_(
                [MeetingStatus.scheduled, MeetingStatus.in_progress]
            ),
            Meeting.is_archived == False,  # noqa: E712
        )
        .order_by(Meeting.scheduled_start.asc())
        .all()
    )
    past = (
        Meeting.query.filter(
            Meeting.status.in_(
                [MeetingStatus.adjourned, MeetingStatus.cancelled]
            ),
            Meeting.is_archived == False,  # noqa: E712
        )
        .order_by(Meeting.scheduled_start.desc())
        .limit(50)
        .all()
    )
    return render_template(
        "meetings/list.html",
        upcoming=upcoming,
        past=past,
        archived=[],
        show_archived=False,
        now=now,
    )


@bp.route("/new", methods=["GET", "POST"])
@role_required(Role.chair, Role.vice_chair, Role.pastor)
def create_meeting():
    form = MeetingForm()
    _populate_board_choices(form)
    _populate_acting_chair_choices(form)
    if form.validate_on_submit():
        acting_chair_id = form.acting_chair_id.data
        meeting = Meeting(
            title=form.title.data.strip(),
            board_id=form.board_id.data,
            meeting_type=MeetingType(form.meeting_type.data),
            scheduled_start=form.scheduled_start.data,
            scheduled_end=form.scheduled_end.data,
            location=(form.location.data or "").strip(),
            status=MeetingStatus.scheduled,
            current_stage=MeetingStage.not_started,
            created_by_id=current_user.id,
            acting_chair_id=acting_chair_id if acting_chair_id else None,
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
@role_required(Role.chair, Role.vice_chair, Role.pastor)
def edit_meeting(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    if meeting.status == MeetingStatus.adjourned:
        abort(403)
    form = MeetingForm(obj=meeting)
    _populate_board_choices(form)
    _populate_acting_chair_choices(form)
    if not form.is_submitted():
        form.meeting_type.data = meeting.meeting_type.value
        form.board_id.data = meeting.board_id
        form.acting_chair_id.data = meeting.acting_chair_id or 0
    if form.validate_on_submit():
        acting_chair_id = form.acting_chair_id.data
        meeting.title = form.title.data.strip()
        meeting.board_id = form.board_id.data
        meeting.meeting_type = MeetingType(form.meeting_type.data)
        meeting.scheduled_start = form.scheduled_start.data
        meeting.scheduled_end = form.scheduled_end.data
        meeting.location = (form.location.data or "").strip()
        meeting.acting_chair_id = acting_chair_id if acting_chair_id else None
        db.session.commit()
        flash("Meeting updated.", "success")
        return redirect(
            url_for("meetings.meeting_detail", meeting_id=meeting.id)
        )
    return render_template(
        "meetings/form.html", form=form, action="edit", meeting=meeting
    )


@bp.route("/<int:meeting_id>/cancel", methods=["POST"])
@role_required(Role.chair, Role.vice_chair, Role.pastor)
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


@bp.route("/<int:meeting_id>/kiosk-link", methods=["POST"])
@login_required
def kiosk_link(meeting_id: int):
    """Generate a kiosk check-in link for a meeting."""
    if current_user.role.value not in SECRETARY_ROLES:
        abort(403)
    meeting = Meeting.query.get_or_404(meeting_id)
    token = generate_kiosk_token(meeting.id)
    return redirect(url_for("kiosk.checkin_page", token=token))


@bp.route("/<int:meeting_id>/archive", methods=["POST"])
@admin_required
def archive_meeting(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    meeting.is_archived = True
    meeting.archived_at = now_eastern()
    meeting.archived_by_id = current_user.id
    log_admin_action(
        current_user.id, "archive_meeting", "meeting", meeting.id,
        f'Archived meeting "{meeting.title}".',
    )
    db.session.commit()
    flash("Meeting archived.", "info")
    return redirect(url_for("meetings.list_meetings"))


@bp.route("/<int:meeting_id>/unarchive", methods=["POST"])
@admin_required
def unarchive_meeting(meeting_id: int):
    meeting = Meeting.query.get_or_404(meeting_id)
    meeting.is_archived = False
    meeting.archived_at = None
    meeting.archived_by_id = None
    log_admin_action(
        current_user.id, "unarchive_meeting", "meeting", meeting.id,
        f'Restored meeting "{meeting.title}" from archive.',
    )
    db.session.commit()
    flash("Meeting restored from archive.", "success")
    return redirect(url_for("meetings.list_meetings"))


# ---------------------------------------------------------------------------
# Meeting Templates
# ---------------------------------------------------------------------------


@bp.route("/templates")
@login_required
def list_templates():
    templates = (
        MeetingTemplate.query
        .order_by(MeetingTemplate.name)
        .all()
    )
    return render_template("meetings/templates.html", templates=templates)


@bp.route("/templates/new", methods=["GET", "POST"])
@role_required(Role.chair, Role.vice_chair, Role.secretary, Role.pastor)
def create_template():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not name:
            flash("Template name is required.", "danger")
            return render_template("meetings/template_form.html", action="new")

        template = MeetingTemplate(
            name=name,
            description=description,
            created_by_id=current_user.id,
        )
        db.session.add(template)
        db.session.flush()

        # Parse items from form.
        idx = 0
        while f"item_title_{idx}" in request.form:
            title = (request.form.get(f"item_title_{idx}") or "").strip()
            category = request.form.get(f"item_category_{idx}", "new_business")
            if title:
                item = MeetingTemplateItem(
                    template_id=template.id,
                    order_index=idx,
                    category=AgendaCategory(category),
                    title=title,
                    description=(request.form.get(f"item_desc_{idx}") or "").strip(),
                    is_confidential=bool(request.form.get(f"item_confidential_{idx}")),
                )
                db.session.add(item)
            idx += 1

        db.session.commit()
        flash(f'Template "{name}" created.', "success")
        return redirect(url_for("meetings.list_templates"))

    return render_template("meetings/template_form.html", action="new")


@bp.route("/templates/<int:template_id>")
@login_required
def view_template(template_id: int):
    template = MeetingTemplate.query.get_or_404(template_id)
    return render_template("meetings/template_detail.html", template=template)


@bp.route("/templates/<int:template_id>/delete", methods=["POST"])
@admin_required
def delete_template(template_id: int):
    template = MeetingTemplate.query.get_or_404(template_id)
    name = template.name
    db.session.delete(template)
    db.session.commit()
    flash(f'Template "{name}" deleted.', "info")
    return redirect(url_for("meetings.list_templates"))


@bp.route("/<int:meeting_id>/save-as-template", methods=["POST"])
@role_required(Role.chair, Role.vice_chair, Role.secretary, Role.pastor)
def save_as_template(meeting_id: int):
    """Save an existing meeting's agenda as a template."""
    meeting = Meeting.query.get_or_404(meeting_id)
    name = request.form.get("template_name", "").strip()
    if not name:
        name = f"Template from {meeting.title}"

    template = MeetingTemplate(
        name=name,
        description=f"Created from meeting: {meeting.title}",
        meeting_type=meeting.meeting_type,
        created_by_id=current_user.id,
    )
    db.session.add(template)
    db.session.flush()

    for item in meeting.agenda_items:
        db.session.add(MeetingTemplateItem(
            template_id=template.id,
            order_index=item.order_index,
            category=item.category,
            title=item.title,
            description=item.description or "",
            is_confidential=item.is_confidential,
        ))

    db.session.commit()
    flash(f'Saved agenda as template "{name}".', "success")
    return redirect(url_for("meetings.meeting_detail", meeting_id=meeting_id))


@bp.route("/<int:meeting_id>/apply-template", methods=["POST"])
@role_required(Role.chair, Role.vice_chair, Role.secretary, Role.pastor)
def apply_template(meeting_id: int):
    """Apply a template's agenda items to a meeting."""
    meeting = Meeting.query.get_or_404(meeting_id)
    template_id = request.form.get("template_id", type=int)
    if not template_id:
        flash("No template selected.", "warning")
        return redirect(url_for("agendas.view_agenda", meeting_id=meeting_id))

    template = MeetingTemplate.query.get_or_404(template_id)
    max_order = max((i.order_index for i in meeting.agenda_items), default=0)

    for item in template.items:
        db.session.add(AgendaItem(
            meeting_id=meeting.id,
            order_index=max_order + item.order_index + 1,
            category=item.category,
            title=item.title,
            description=item.description,
            is_confidential=item.is_confidential,
        ))

    db.session.commit()
    flash(f'Applied template "{template.name}" ({len(template.items)} items).', "success")
    return redirect(url_for("agendas.view_agenda", meeting_id=meeting_id))

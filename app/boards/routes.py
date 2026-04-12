"""Board service-term tracking routes."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..admin_log import log_admin_action
from ..extensions import db
from ..models import (
    Board,
    BoardMembership,
    BoardRole,
    Meeting,
    MeetingType,
    ServiceTerm,
    TERM_RULES,
    TermStatus,
    User,
    compute_term_end,
    compute_term_start,
    cooldown_end_date,
    count_consecutive_terms,
    is_eligible_for_term,
)
from ..permissions import admin_required
from . import bp
from .forms import (
    BoardMembershipForm,
    EditMembershipForm,
    EditTermForm,
    EndTermForm,
    RecordTermForm,
)


@bp.route("/")
@login_required
def list_boards():
    boards = Board.query.order_by(Board.display_name).all()
    today = date.today()
    # Count terms expiring within 6 months per board.
    expiring_counts: dict[int, int] = {}
    for b in boards:
        six_months = date(
            today.year + (1 if today.month > 6 else 0),
            (today.month + 6 - 1) % 12 + 1,
            today.day if today.day <= 28 else 28,
        )
        count = (
            ServiceTerm.query
            .filter_by(board_id=b.id, status=TermStatus.active)
            .filter(ServiceTerm.term_end <= six_months)
            .count()
        )
        expiring_counts[b.id] = count
    return render_template(
        "boards/list.html",
        boards=boards,
        expiring_counts=expiring_counts,
    )


@bp.route("/<slug>")
@login_required
def board_detail(slug: str):
    board = Board.query.filter_by(slug=slug).first_or_404()
    today = date.today()

    # Current active terms.
    active_terms = (
        ServiceTerm.query
        .filter_by(board_id=board.id, status=TermStatus.active)
        .order_by(ServiceTerm.term_end.asc())
        .all()
    )

    # Terms expiring within 6 months.
    six_months = date(
        today.year + (1 if today.month > 6 else 0),
        (today.month + 6 - 1) % 12 + 1,
        today.day if today.day <= 28 else 28,
    )
    expiring_terms = [t for t in active_terms if t.term_end <= six_months]

    # Cooldown members: users who served max terms and are cooling down.
    cooldown_members: list[dict] = []
    completed_terms = (
        ServiceTerm.query
        .filter_by(board_id=board.id, status=TermStatus.completed)
        .all()
    )
    seen_users: set[tuple[int, str]] = set()
    for t in completed_terms:
        key = (t.user_id, t.role_on_board.value)
        if key in seen_users:
            continue
        seen_users.add(key)
        cd_end = cooldown_end_date(t.user_id, board.id, t.role_on_board.value)
        if cd_end and today < cd_end:
            months_left = max(0, (cd_end - today).days // 30)
            cooldown_members.append({
                "user": t.user,
                "role": t.role_on_board,
                "cooldown_end": cd_end,
                "months_left": months_left,
            })

    # Past (non-active) terms for history.
    past_terms = (
        ServiceTerm.query
        .filter_by(board_id=board.id)
        .filter(ServiceTerm.status != TermStatus.active)
        .order_by(ServiceTerm.term_start.desc())
        .all()
    )

    return render_template(
        "boards/detail.html",
        board=board,
        active_terms=active_terms,
        expiring_terms=expiring_terms,
        cooldown_members=cooldown_members,
        past_terms=past_terms,
        today=today,
        term_rules=TERM_RULES,
    )


@bp.route("/<slug>/record-term", methods=["GET", "POST"])
@admin_required
def record_term(slug: str):
    board = Board.query.filter_by(slug=slug).first_or_404()
    form = RecordTermForm()

    # Populate dynamic choices.
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    form.user_id.choices = [(u.id, u.full_name) for u in users]

    annual_meetings = (
        Meeting.query
        .filter(Meeting.meeting_type.in_([
            MeetingType.annual_business,
            MeetingType.special_business,
        ]))
        .order_by(Meeting.scheduled_start.desc())
        .all()
    )
    form.elected_at_meeting_id.choices = [(0, "— None —")] + [
        (m.id, f"{m.title} ({m.scheduled_start.strftime('%b %Y')})")
        for m in annual_meetings
    ]

    if form.validate_on_submit():
        role_value = form.role_on_board.data
        term_start = form.term_start.data
        term_end = compute_term_end(term_start, role_value)
        term_status = TermStatus(form.status.data)

        # Determine consecutive term number.
        consecutive = count_consecutive_terms(
            form.user_id.data, board.id, role_value
        )
        term_number = consecutive + 1

        # Check eligibility (warn but don't block).
        # Skip for completed historical terms — the election already happened.
        if term_status == TermStatus.active:
            eligible, reason = is_eligible_for_term(
                form.user_id.data, board.id, role_value
            )
            if not eligible:
                flash(f"Warning: {reason}. Recording term anyway.", "warning")

        meeting_id = form.elected_at_meeting_id.data
        term = ServiceTerm(
            board_id=board.id,
            user_id=form.user_id.data,
            role_on_board=BoardRole(role_value),
            elected_at_meeting_id=meeting_id if meeting_id else None,
            term_start=term_start,
            term_end=term_end,
            term_number=term_number,
            status=term_status,
            notes=(form.notes.data or "").strip(),
        )
        db.session.add(term)

        # Ensure the user has a BoardMembership on this board
        # (only for active terms — completed terms are historical).
        if term_status == TermStatus.active:
            existing = BoardMembership.query.filter_by(
                board_id=board.id, user_id=form.user_id.data
            ).first()
            if not existing:
                db.session.add(BoardMembership(
                    board_id=board.id,
                    user_id=form.user_id.data,
                    role_on_board=BoardRole(role_value),
                    is_voting=True,
                ))

        db.session.flush()
        user = db.session.get(User, form.user_id.data)
        log_admin_action(
            current_user.id, "record_service_term", "service_term", term.id,
            f"Recorded {role_value} term for {user.full_name} on {board.display_name}.",
        )
        db.session.commit()
        label = "active" if term_status == TermStatus.active else "completed"
        flash(
            f"Recorded {label} term for {term.user.full_name}: "
            f"{term_start.strftime('%b %Y')} – {term_end.strftime('%b %Y')}.",
            "success",
        )
        return redirect(url_for("boards.board_detail", slug=slug))

    # Auto-populate term_start from the selected meeting (for GET requests).
    if not form.is_submitted() and annual_meetings:
        meeting = annual_meetings[0]
        form.term_start.data = compute_term_start(meeting.scheduled_start)
        form.elected_at_meeting_id.data = meeting.id

    # Compute preview of term end for the template.
    term_end_preview = None
    if form.term_start.data and form.role_on_board.data:
        try:
            term_end_preview = compute_term_end(
                form.term_start.data, form.role_on_board.data
            )
        except (ValueError, TypeError):
            pass

    return render_template(
        "boards/record_term.html",
        board=board,
        form=form,
        term_rules=TERM_RULES,
        term_end_preview=term_end_preview,
    )


@bp.route("/terms/<int:term_id>/end", methods=["GET", "POST"])
@admin_required
def end_term(term_id: int):
    term = ServiceTerm.query.get_or_404(term_id)
    board = term.board
    form = EndTermForm()

    if form.validate_on_submit():
        term.actual_end = form.actual_end.data
        term.status = TermStatus(form.status.data)
        if form.notes.data:
            term.notes = (
                (term.notes + "\n" if term.notes else "")
                + form.notes.data.strip()
            )
        log_admin_action(
            current_user.id, "end_service_term", "service_term", term.id,
            f"Ended {term.user.full_name}'s term as "
            f"{term.role_on_board.value.replace('_', ' ')} on {board.display_name}.",
        )
        db.session.commit()
        flash(
            f"Ended {term.user.full_name}'s term as "
            f"{term.role_on_board.value.replace('_', ' ')}.",
            "info",
        )
        return redirect(url_for("boards.board_detail", slug=board.slug))

    if not form.is_submitted():
        form.actual_end.data = date.today()

    return render_template(
        "boards/end_term.html",
        board=board,
        term=term,
        form=form,
    )


# ---------------------------------------------------------------------------
# Board membership management
# ---------------------------------------------------------------------------


@bp.route("/<slug>/members/add", methods=["GET", "POST"])
@admin_required
def add_member(slug: str):
    board = Board.query.filter_by(slug=slug).first_or_404()
    form = BoardMembershipForm()

    # Only show active users not already on this board.
    existing_user_ids = {
        m.user_id for m in BoardMembership.query.filter_by(board_id=board.id).all()
    }
    available_users = (
        User.query
        .filter_by(is_active=True)
        .filter(~User.id.in_(existing_user_ids) if existing_user_ids else User.id.isnot(None))
        .order_by(User.full_name)
        .all()
    )
    form.user_id.choices = [(u.id, u.full_name) for u in available_users]

    if form.validate_on_submit():
        membership = BoardMembership(
            board_id=board.id,
            user_id=form.user_id.data,
            role_on_board=BoardRole(form.role_on_board.data),
            is_voting=form.is_voting.data,
        )
        db.session.add(membership)
        db.session.flush()
        user = db.session.get(User, form.user_id.data)
        log_admin_action(
            current_user.id, "add_board_member", "board_membership", membership.id,
            f"Added {user.full_name} to {board.display_name} as "
            f"{form.role_on_board.data.replace('_', ' ')}.",
        )
        db.session.commit()
        flash(f"Added {user.full_name} to {board.display_name}.", "success")
        return redirect(url_for("boards.board_detail", slug=slug))

    return render_template(
        "boards/add_member.html",
        board=board,
        form=form,
    )


@bp.route("/<slug>/members/<int:membership_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_member(slug: str, membership_id: int):
    board = Board.query.filter_by(slug=slug).first_or_404()
    membership = BoardMembership.query.get_or_404(membership_id)
    if membership.board_id != board.id:
        abort(404)

    form = EditMembershipForm(obj=membership)

    if form.validate_on_submit():
        membership.role_on_board = BoardRole(form.role_on_board.data)
        membership.is_voting = form.is_voting.data
        log_admin_action(
            current_user.id, "edit_board_member", "board_membership", membership.id,
            f"Updated {membership.user.full_name}'s membership on {board.display_name}: "
            f"role={form.role_on_board.data.replace('_', ' ')}, voting={form.is_voting.data}.",
        )
        db.session.commit()
        flash(f"Updated {membership.user.full_name}'s membership.", "success")
        return redirect(url_for("boards.board_detail", slug=slug))

    if not form.is_submitted():
        form.role_on_board.data = membership.role_on_board.value

    return render_template(
        "boards/edit_member.html",
        board=board,
        membership=membership,
        form=form,
    )


@bp.route("/<slug>/members/<int:membership_id>/remove", methods=["POST"])
@admin_required
def remove_member(slug: str, membership_id: int):
    board = Board.query.filter_by(slug=slug).first_or_404()
    membership = BoardMembership.query.get_or_404(membership_id)
    if membership.board_id != board.id:
        abort(404)

    user_name = membership.user.full_name
    log_admin_action(
        current_user.id, "remove_board_member", "board_membership", membership.id,
        f"Removed {user_name} from {board.display_name}.",
    )
    db.session.delete(membership)
    db.session.commit()
    flash(f"Removed {user_name} from {board.display_name}.", "info")
    return redirect(url_for("boards.board_detail", slug=slug))


# ---------------------------------------------------------------------------
# Service term editing
# ---------------------------------------------------------------------------


@bp.route("/terms/<int:term_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_term(term_id: int):
    term = ServiceTerm.query.get_or_404(term_id)
    board = term.board
    form = EditTermForm(obj=term)

    if form.validate_on_submit():
        term.term_start = form.term_start.data
        term.term_end = form.term_end.data
        term.status = TermStatus(form.status.data)
        term.notes = (form.notes.data or "").strip()
        log_admin_action(
            current_user.id, "edit_service_term", "service_term", term.id,
            f"Edited {term.user.full_name}'s {term.role_on_board.value.replace('_', ' ')} "
            f"term on {board.display_name}.",
        )
        db.session.commit()
        flash(f"Updated {term.user.full_name}'s service term.", "success")
        return redirect(url_for("boards.board_detail", slug=board.slug))

    if not form.is_submitted():
        form.status.data = term.status.value

    return render_template(
        "boards/edit_term.html",
        board=board,
        term=term,
        form=form,
    )


# ---------------------------------------------------------------------------
# Term expiration calendar
# ---------------------------------------------------------------------------


@bp.route("/term-calendar")
@login_required
def term_calendar():
    """Visual timeline of all active service terms grouped by expiration month."""
    today = date.today()
    active_terms = (
        ServiceTerm.query
        .filter_by(status=TermStatus.active)
        .order_by(ServiceTerm.term_end.asc())
        .all()
    )

    # Group terms by expiration month (YYYY-MM string key).
    by_month: dict[str, list] = defaultdict(list)
    for t in active_terms:
        key = t.term_end.strftime("%Y-%m")
        by_month[key].append(t)

    # Build ordered list of (month_label, terms) tuples.
    month_groups = []
    for key in sorted(by_month.keys()):
        sample = by_month[key][0].term_end
        label = sample.strftime("%B %Y")
        is_past = sample < today
        months_away = (sample.year - today.year) * 12 + (sample.month - today.month)
        month_groups.append({
            "key": key,
            "label": label,
            "terms": by_month[key],
            "is_past": is_past,
            "months_away": months_away,
        })

    # Cooldown members across all boards.
    cooldown_members: list[dict] = []
    completed_terms = (
        ServiceTerm.query
        .filter_by(status=TermStatus.completed)
        .all()
    )
    seen: set[tuple[int, int, str]] = set()
    for t in completed_terms:
        key = (t.user_id, t.board_id, t.role_on_board.value)
        if key in seen:
            continue
        seen.add(key)
        cd_end = cooldown_end_date(t.user_id, t.board_id, t.role_on_board.value)
        if cd_end and today < cd_end:
            cooldown_members.append({
                "user": t.user,
                "role": t.role_on_board,
                "board": t.board,
                "cooldown_end": cd_end,
                "months_left": max(0, (cd_end - today).days // 30),
            })

    return render_template(
        "boards/term_calendar.html",
        month_groups=month_groups,
        cooldown_members=cooldown_members,
        today=today,
        term_rules=TERM_RULES,
    )

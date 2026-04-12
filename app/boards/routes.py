"""Board service-term tracking routes."""
from __future__ import annotations

from datetime import date

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

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
from .forms import EndTermForm, RecordTermForm


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

        # Determine consecutive term number.
        consecutive = count_consecutive_terms(
            form.user_id.data, board.id, role_value
        )
        term_number = consecutive + 1

        # Check eligibility (warn but don't block).
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
            status=TermStatus.active,
            notes=(form.notes.data or "").strip(),
        )
        db.session.add(term)

        # Ensure the user has a BoardMembership on this board.
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

        db.session.commit()
        flash(
            f"Recorded term for {term.user.full_name}: "
            f"{term_start.strftime('%b %Y')} – {term_end.strftime('%b %Y')}.",
            "success",
        )
        return redirect(url_for("boards.board_detail", slug=slug))

    # Auto-populate term_start from the selected meeting (for GET requests).
    if not form.is_submitted() and annual_meetings:
        meeting = annual_meetings[0]
        form.term_start.data = compute_term_start(meeting.scheduled_start)
        form.elected_at_meeting_id.data = meeting.id

    return render_template(
        "boards/record_term.html",
        board=board,
        form=form,
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

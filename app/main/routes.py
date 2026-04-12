from datetime import date, datetime

from flask import render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func

from ..extensions import db
from ..models import (
    AdminAction,
    Meeting,
    MeetingAttendance,
    MeetingStatus,
    Motion,
    MotionResult,
    Report,
    ServiceTerm,
    TermStatus,
    User,
    Vote,
)
from ..permissions import CHAIR_ROLES, SECRETARY_ROLES, admin_required
from ..utils import now_eastern
from . import bp


def _six_months_from(today: date) -> date:
    return date(
        today.year + (1 if today.month > 6 else 0),
        (today.month + 6 - 1) % 12 + 1,
        today.day if today.day <= 28 else 28,
    )


@bp.route("/")
@login_required
def dashboard():
    now = now_eastern()
    today = date.today()
    role = current_user.role.value

    # ── Common queries (all roles) ──
    in_progress = (
        Meeting.query.filter_by(status=MeetingStatus.in_progress, is_archived=False)
        .order_by(Meeting.scheduled_start.asc())
        .all()
    )
    upcoming = (
        Meeting.query.filter(
            Meeting.status.in_(
                [MeetingStatus.scheduled, MeetingStatus.in_progress]
            ),
            Meeting.is_archived == False,  # noqa: E712
        )
        .filter(Meeting.scheduled_start >= now)
        .order_by(Meeting.scheduled_start.asc())
        .limit(5)
        .all()
    )
    recent = (
        Meeting.query.filter_by(status=MeetingStatus.adjourned, is_archived=False)
        .order_by(Meeting.adjourned_at.desc())
        .limit(5)
        .all()
    )

    # ── Role-specific data ──
    pending_reports = None
    expiring_terms = None
    unapproved_minutes = None
    recent_admin_actions = None
    total_users = None
    active_users = None

    # Secretary/chair: pending reports, unapproved minutes
    if role in SECRETARY_ROLES:
        pending_reports = (
            Report.query.filter(
                Report.approved_at.is_(None),
                Report.is_archived == False,  # noqa: E712
            )
            .order_by(Report.submitted_at.desc())
            .limit(5)
            .all()
        )
        unapproved_minutes = (
            Meeting.query.filter(
                Meeting.status == MeetingStatus.adjourned,
                Meeting.minutes_approved_at.is_(None),
                Meeting.is_archived == False,  # noqa: E712
            )
            .order_by(Meeting.adjourned_at.desc())
            .limit(5)
            .all()
        )

    # Chair/admin: expiring terms
    if role in CHAIR_ROLES:
        six_months = _six_months_from(today)
        expiring_terms = (
            ServiceTerm.query
            .filter_by(status=TermStatus.active)
            .filter(ServiceTerm.term_end <= six_months)
            .order_by(ServiceTerm.term_end.asc())
            .all()
        )

    # Admin: system stats + recent actions
    if role == "admin":
        if pending_reports is None:
            pending_reports = (
                Report.query.filter(
                    Report.approved_at.is_(None),
                    Report.is_archived == False,  # noqa: E712
                )
                .order_by(Report.submitted_at.desc())
                .limit(5)
                .all()
            )
        if expiring_terms is None:
            six_months = _six_months_from(today)
            expiring_terms = (
                ServiceTerm.query
                .filter_by(status=TermStatus.active)
                .filter(ServiceTerm.term_end <= six_months)
                .order_by(ServiceTerm.term_end.asc())
                .all()
            )
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        recent_admin_actions = (
            AdminAction.query
            .order_by(AdminAction.created_at.desc())
            .limit(5)
            .all()
        )

    return render_template(
        "main/dashboard.html",
        upcoming=upcoming,
        in_progress=in_progress,
        recent=recent,
        pending_reports=pending_reports,
        expiring_terms=expiring_terms,
        unapproved_minutes=unapproved_minutes,
        recent_admin_actions=recent_admin_actions,
        total_users=total_users,
        active_users=active_users,
    )


@bp.route("/guide")
@login_required
def guide():
    return render_template("main/guide.html")


@bp.route("/about")
@login_required
def about():
    return render_template("main/about.html")


@bp.route("/annual-report")
@admin_required
def annual_report():
    """Generate an annual statistics report for a given year."""
    year = request.args.get("year", date.today().year, type=int)
    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31, 23, 59, 59)

    # Meetings held this year.
    meetings = (
        Meeting.query
        .filter(
            Meeting.status == MeetingStatus.adjourned,
            Meeting.scheduled_start >= year_start,
            Meeting.scheduled_start <= year_end,
        )
        .order_by(Meeting.scheduled_start.asc())
        .all()
    )

    # Attendance stats.
    total_attendance = 0
    total_possible = 0
    member_attendance: dict[int, dict] = {}
    for m in meetings:
        for a in m.attendances:
            uid = a.user_id
            if uid not in member_attendance:
                member_attendance[uid] = {
                    "user": a.user,
                    "present": 0,
                    "total": 0,
                }
            member_attendance[uid]["total"] += 1
            total_possible += 1
            if a.is_present:
                member_attendance[uid]["present"] += 1
                total_attendance += 1

    attendance_rate = (
        round(total_attendance / total_possible * 100, 1)
        if total_possible > 0
        else 0
    )

    # Sort members by attendance rate descending.
    attendance_list = sorted(
        member_attendance.values(),
        key=lambda x: x["present"] / max(x["total"], 1),
        reverse=True,
    )

    # Motions.
    motions_passed = (
        Motion.query
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.scheduled_start >= year_start,
            Meeting.scheduled_start <= year_end,
            Motion.result == MotionResult.passed,
        )
        .count()
    )
    motions_failed = (
        Motion.query
        .join(Meeting, Motion.meeting_id == Meeting.id)
        .filter(
            Meeting.scheduled_start >= year_start,
            Meeting.scheduled_start <= year_end,
            Motion.result == MotionResult.failed,
        )
        .count()
    )

    # Reports submitted.
    reports_count = (
        Report.query
        .filter(
            Report.submitted_at >= year_start,
            Report.submitted_at <= year_end,
        )
        .count()
    )

    # Terms started/ended.
    terms_started = (
        ServiceTerm.query
        .filter(
            ServiceTerm.term_start >= date(year, 1, 1),
            ServiceTerm.term_start <= date(year, 12, 31),
        )
        .count()
    )
    terms_ended = (
        ServiceTerm.query
        .filter(
            ServiceTerm.status != TermStatus.active,
            ServiceTerm.term_end >= date(year, 1, 1),
            ServiceTerm.term_end <= date(year, 12, 31),
        )
        .count()
    )

    # User stats.
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()

    # Meeting type breakdown.
    type_counts: dict[str, int] = {}
    for m in meetings:
        label = m.meeting_type.value.replace("_", " ").title()
        type_counts[label] = type_counts.get(label, 0) + 1

    return render_template(
        "main/annual_report.html",
        year=year,
        meetings=meetings,
        meeting_count=len(meetings),
        type_counts=type_counts,
        attendance_rate=attendance_rate,
        attendance_list=attendance_list,
        motions_passed=motions_passed,
        motions_failed=motions_failed,
        reports_count=reports_count,
        terms_started=terms_started,
        terms_ended=terms_ended,
        total_users=total_users,
        active_users=active_users,
    )

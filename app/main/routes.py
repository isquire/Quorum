from datetime import date, datetime

from flask import render_template
from flask_login import login_required

from ..models import Meeting, MeetingStatus, Report, ServiceTerm, TermStatus
from . import bp


@bp.route("/")
@login_required
def dashboard():
    now = datetime.utcnow()
    upcoming = (
        Meeting.query.filter(
            Meeting.status.in_(
                [MeetingStatus.scheduled, MeetingStatus.in_progress]
            )
        )
        .filter(Meeting.scheduled_start >= now)
        .order_by(Meeting.scheduled_start.asc())
        .limit(5)
        .all()
    )
    in_progress = (
        Meeting.query.filter_by(status=MeetingStatus.in_progress)
        .order_by(Meeting.scheduled_start.asc())
        .all()
    )
    recent = (
        Meeting.query.filter_by(status=MeetingStatus.adjourned)
        .order_by(Meeting.adjourned_at.desc())
        .limit(5)
        .all()
    )
    pending_reports = (
        Report.query.filter(Report.approved_at.is_(None))
        .order_by(Report.submitted_at.desc())
        .limit(5)
        .all()
    )

    # Terms expiring within 6 months.
    today = date.today()
    six_months = date(
        today.year + (1 if today.month > 6 else 0),
        (today.month + 6 - 1) % 12 + 1,
        today.day if today.day <= 28 else 28,
    )
    expiring_terms = (
        ServiceTerm.query
        .filter_by(status=TermStatus.active)
        .filter(ServiceTerm.term_end <= six_months)
        .order_by(ServiceTerm.term_end.asc())
        .all()
    )

    return render_template(
        "main/dashboard.html",
        upcoming=upcoming,
        in_progress=in_progress,
        recent=recent,
        pending_reports=pending_reports,
        expiring_terms=expiring_terms,
    )


@bp.route("/guide")
@login_required
def guide():
    return render_template("main/guide.html")


@bp.route("/about")
@login_required
def about():
    return render_template("main/about.html")

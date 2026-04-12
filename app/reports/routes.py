from datetime import datetime

from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Meeting, Report, ReportType, Role
from ..permissions import role_required
from . import bp
from .forms import ReportForm


def _populate_meeting_choices(form: ReportForm) -> None:
    meetings = Meeting.query.order_by(Meeting.scheduled_start.desc()).all()
    form.meeting_id.choices = [(0, "— unlinked —")] + [
        (m.id, f"{m.title} ({m.scheduled_start:%Y-%m-%d})") for m in meetings
    ]


@bp.route("/")
@login_required
def list_reports():
    reports = Report.query.order_by(Report.submitted_at.desc()).all()
    return render_template("reports/list.html", reports=reports)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create_report():
    form = ReportForm()
    _populate_meeting_choices(form)

    if form.validate_on_submit():
        report_type = ReportType(form.report_type.data)
        # Only treasurer (or admin) may file a treasurer report.
        if report_type == ReportType.treasurer and current_user.role not in {
            Role.admin,
            Role.treasurer,
        }:
            abort(403)

        meeting_id = form.meeting_id.data or None
        if meeting_id == 0:
            meeting_id = None

        report = Report(
            title=form.title.data.strip(),
            report_type=report_type,
            committee=(form.committee.data or "").strip(),
            content=(form.content.data or "").strip(),
            submitted_by_id=current_user.id,
            meeting_id=meeting_id,
            period_start=form.period_start.data,
            period_end=form.period_end.data,
            submitted_at=datetime.utcnow(),
        )
        db.session.add(report)
        db.session.commit()
        flash("Report submitted.", "success")
        return redirect(url_for("reports.detail", report_id=report.id))

    return render_template("reports/form.html", form=form, action="new")


@bp.route("/<int:report_id>")
@login_required
def detail(report_id: int):
    report = Report.query.get_or_404(report_id)
    return render_template("reports/detail.html", report=report)


@bp.route("/<int:report_id>/approve", methods=["POST"])
@role_required(Role.chair, Role.vice_chair)
def approve(report_id: int):
    report = Report.query.get_or_404(report_id)
    report.approved_at = datetime.utcnow()
    report.approved_by_id = current_user.id
    db.session.commit()
    flash("Report approved.", "success")
    return redirect(url_for("reports.detail", report_id=report_id))

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..admin_log import log_admin_action
from ..extensions import db
from ..models import Meeting, Report, ReportType, Role
from ..permissions import admin_required, role_required
from ..utils import now_eastern
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
    show = request.args.get("show", "")
    if show == "archived":
        reports = (
            Report.query.filter_by(is_archived=True)
            .order_by(Report.submitted_at.desc())
            .all()
        )
    else:
        reports = (
            Report.query.filter_by(is_archived=False)
            .order_by(Report.submitted_at.desc())
            .all()
        )
    return render_template(
        "reports/list.html",
        reports=reports,
        show_archived=(show == "archived"),
    )


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
            submitted_at=now_eastern(),
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
    report.approved_at = now_eastern()
    report.approved_by_id = current_user.id
    db.session.commit()
    flash("Report approved.", "success")
    return redirect(url_for("reports.detail", report_id=report_id))


@bp.route("/<int:report_id>/archive", methods=["POST"])
@admin_required
def archive_report(report_id: int):
    report = Report.query.get_or_404(report_id)
    report.is_archived = True
    report.archived_at = now_eastern()
    report.archived_by_id = current_user.id
    log_admin_action(
        current_user.id, "archive_report", "report", report.id,
        f'Archived report "{report.title}".',
    )
    db.session.commit()
    flash("Report archived.", "info")
    return redirect(url_for("reports.list_reports"))


@bp.route("/<int:report_id>/unarchive", methods=["POST"])
@admin_required
def unarchive_report(report_id: int):
    report = Report.query.get_or_404(report_id)
    report.is_archived = False
    report.archived_at = None
    report.archived_by_id = None
    log_admin_action(
        current_user.id, "unarchive_report", "report", report.id,
        f'Restored report "{report.title}" from archive.',
    )
    db.session.commit()
    flash("Report restored from archive.", "success")
    return redirect(url_for("reports.list_reports"))

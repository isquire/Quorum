from flask import (
    abort,
    current_app,
    flash,
    redirect,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from ..extensions import db
from ..models import AgendaItem, Attachment, Document, Meeting, Report, Role
from ..utils import allowed_upload, save_upload, upload_path
from . import bp


@bp.route("/upload", methods=["POST"])
@login_required
def upload():
    context_type = request.form.get("context_type")
    context_id = request.form.get("context_id", type=int)
    file = request.files.get("file")

    if not file or not file.filename:
        flash("No file selected.", "warning")
        return redirect(request.referrer or url_for("main.dashboard"))

    if not allowed_upload(file.filename):
        flash("File type not allowed.", "danger")
        return redirect(request.referrer or url_for("main.dashboard"))

    kwargs: dict = {}
    if context_type == "meeting":
        meeting = Meeting.query.get_or_404(context_id)
        kwargs["meeting_id"] = meeting.id
        back = url_for("meetings.meeting_detail", meeting_id=meeting.id)
    elif context_type == "agenda_item":
        item = AgendaItem.query.get_or_404(context_id)
        kwargs["agenda_item_id"] = item.id
        back = url_for("agendas.view_agenda", meeting_id=item.meeting_id)
    elif context_type == "report":
        report = Report.query.get_or_404(context_id)
        if report.submitted_by_id != current_user.id and current_user.role != Role.admin:
            abort(403)
        kwargs["report_id"] = report.id
        back = url_for("reports.detail", report_id=report.id)
    elif context_type == "document":
        doc = Document.query.get_or_404(context_id)
        if current_user.role != Role.admin:
            abort(403)
        kwargs["document_id"] = doc.id
        back = url_for("documents.view_document", doc_id=doc.id)
    else:
        abort(400)

    stored, size = save_upload(file)
    attachment = Attachment(
        filename=stored,
        original_filename=file.filename,
        mime_type=file.mimetype or "",
        size_bytes=size,
        uploaded_by_id=current_user.id,
        **kwargs,
    )
    db.session.add(attachment)
    db.session.commit()
    flash("File uploaded.", "success")
    return redirect(back)


@bp.route("/<int:attachment_id>")
@login_required
def download(attachment_id: int):
    attachment = Attachment.query.get_or_404(attachment_id)
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        attachment.filename,
        as_attachment=False,
        download_name=attachment.original_filename,
    )


@bp.route("/<int:attachment_id>/delete", methods=["POST"])
@login_required
def delete(attachment_id: int):
    attachment = Attachment.query.get_or_404(attachment_id)
    if (
        attachment.uploaded_by_id != current_user.id
        and current_user.role != Role.admin
    ):
        abort(403)
    try:
        upload_path(attachment.filename).unlink(missing_ok=True)
    except OSError:
        pass
    db.session.delete(attachment)
    db.session.commit()
    flash("File deleted.", "info")
    return redirect(request.referrer or url_for("main.dashboard"))

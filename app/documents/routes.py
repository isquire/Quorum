"""Document repository routes."""
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..admin_log import log_admin_action
from ..extensions import db
from ..models import Document, DocumentCategory, DocumentVersion
from ..permissions import admin_required
from . import bp


@bp.route("/")
@login_required
def list_documents():
    category = request.args.get("category", "")
    query = Document.query.order_by(Document.title)
    if category and category in {c.value for c in DocumentCategory}:
        query = query.filter_by(category=DocumentCategory(category))
    documents = query.all()
    return render_template(
        "documents/list.html",
        documents=documents,
        categories=DocumentCategory,
        selected_category=category,
    )


@bp.route("/<int:doc_id>")
@login_required
def view_document(doc_id: int):
    doc = Document.query.get_or_404(doc_id)
    return render_template("documents/view.html", doc=doc)


@bp.route("/<int:doc_id>/history")
@login_required
def view_history(doc_id: int):
    doc = Document.query.get_or_404(doc_id)
    return render_template("documents/history.html", doc=doc)


@bp.route("/<int:doc_id>/version/<int:version>")
@login_required
def view_version(doc_id: int, version: int):
    doc = Document.query.get_or_404(doc_id)
    ver = DocumentVersion.query.filter_by(
        document_id=doc_id, version=version
    ).first_or_404()
    return render_template("documents/version.html", doc=doc, ver=ver)


@bp.route("/new", methods=["GET", "POST"])
@admin_required
def create_document():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        category = request.form.get("category", "other")
        content = (request.form.get("content") or "").strip()

        if not title:
            flash("Title is required.", "danger")
            return render_template(
                "documents/form.html",
                action="new",
                categories=DocumentCategory,
            )

        doc = Document(
            title=title,
            category=DocumentCategory(category),
            content=content,
            current_version=1,
            updated_by_id=current_user.id,
        )
        db.session.add(doc)
        db.session.flush()

        # Save initial version.
        ver = DocumentVersion(
            document_id=doc.id,
            version=1,
            content=content,
            change_summary="Initial version",
            edited_by_id=current_user.id,
        )
        db.session.add(ver)
        log_admin_action(
            current_user.id, "create_document", "document", doc.id,
            f'Created document "{title}".',
        )
        db.session.commit()
        flash(f'Document "{title}" created.', "success")
        return redirect(url_for("documents.view_document", doc_id=doc.id))

    return render_template(
        "documents/form.html",
        action="new",
        categories=DocumentCategory,
    )


@bp.route("/<int:doc_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_document(doc_id: int):
    doc = Document.query.get_or_404(doc_id)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        category = request.form.get("category", doc.category.value)
        content = (request.form.get("content") or "").strip()
        change_summary = (request.form.get("change_summary") or "").strip()

        if not title:
            flash("Title is required.", "danger")
            return render_template(
                "documents/form.html",
                action="edit",
                doc=doc,
                categories=DocumentCategory,
            )

        doc.title = title
        doc.category = DocumentCategory(category)
        doc.content = content
        doc.current_version += 1
        doc.updated_by_id = current_user.id

        ver = DocumentVersion(
            document_id=doc.id,
            version=doc.current_version,
            content=content,
            change_summary=change_summary or f"Updated to version {doc.current_version}",
            edited_by_id=current_user.id,
        )
        db.session.add(ver)
        log_admin_action(
            current_user.id, "edit_document", "document", doc.id,
            f'Updated document "{title}" to version {doc.current_version}.',
        )
        db.session.commit()
        flash(f'Document "{title}" updated (v{doc.current_version}).', "success")
        return redirect(url_for("documents.view_document", doc_id=doc.id))

    return render_template(
        "documents/form.html",
        action="edit",
        doc=doc,
        categories=DocumentCategory,
    )


@bp.route("/<int:doc_id>/delete", methods=["POST"])
@admin_required
def delete_document(doc_id: int):
    doc = Document.query.get_or_404(doc_id)
    title = doc.title
    log_admin_action(
        current_user.id, "delete_document", "document", doc.id,
        f'Deleted document "{title}".',
    )
    db.session.delete(doc)
    db.session.commit()
    flash(f'Document "{title}" deleted.', "info")
    return redirect(url_for("documents.list_documents"))

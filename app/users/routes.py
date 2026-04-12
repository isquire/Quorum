import csv
import io
import shutil
from pathlib import Path

from flask import current_app, flash, make_response, redirect, render_template, request, send_file, url_for
from flask_login import current_user

from ..admin_log import log_admin_action
from ..extensions import db
from ..models import AdminAction, Role, User
from ..permissions import admin_required
from ..utils import now_eastern
from . import bp
from .forms import CsvUploadForm, ResetPasswordForm, UserCreateForm, UserEditForm

# CSV column headers — order matters for export.
CSV_COLUMNS = [
    "email", "full_name", "role", "is_active", "is_voting_member",
    "is_active_member", "family_group", "committees", "password",
]

VALID_ROLES = {r.value for r in Role}


@bp.route("/")
@admin_required
def list_users():
    show = request.args.get("show", "")
    if show == "removed":
        users = (
            User.query.filter_by(is_active=False)
            .order_by(User.full_name)
            .all()
        )
    else:
        users = (
            User.query.filter_by(is_active=True)
            .order_by(User.full_name)
            .all()
        )
    return render_template(
        "users/list.html",
        users=users,
        show_removed=(show == "removed"),
    )


@bp.route("/new", methods=["GET", "POST"])
@admin_required
def create_user():
    form = UserCreateForm()
    if form.validate_on_submit():
        existing = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if existing:
            flash("A user with that email already exists.", "warning")
        else:
            user = User(
                email=form.email.data.lower().strip(),
                full_name=form.full_name.data.strip(),
                role=Role(form.role.data),
                is_voting_member=form.is_voting_member.data,
                is_active=form.is_active.data,
                is_active_member=form.is_active_member.data,
                family_group=(form.family_group.data or "").strip() or None,
                committees=(form.committees.data or "").strip(),
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()
            log_admin_action(
                current_user.id, "create_user", "user", user.id,
                f"Created user {user.email} with role {user.role.value}.",
            )
            db.session.commit()
            flash(f"Created user {user.email}.", "success")
            return redirect(url_for("users.list_users"))

    return render_template("users/form.html", form=form, action="new")


@bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_user(user_id: int):
    user = User.query.get_or_404(user_id)
    form = UserEditForm(obj=user)
    if form.validate_on_submit():
        user.email = form.email.data.lower().strip()
        user.full_name = form.full_name.data.strip()
        user.role = Role(form.role.data)
        user.is_voting_member = form.is_voting_member.data
        user.is_active = form.is_active.data
        user.is_active_member = form.is_active_member.data
        user.family_group = (form.family_group.data or "").strip() or None
        user.committees = (form.committees.data or "").strip()
        log_admin_action(
            current_user.id, "edit_user", "user", user.id,
            f"Edited user {user.email}.",
        )
        db.session.commit()
        flash("User updated.", "success")
        return redirect(url_for("users.list_users"))

    # Pre-populate select field
    if not form.is_submitted():
        form.role.data = user.role.value
    return render_template(
        "users/form.html", form=form, action="edit", user=user
    )


@bp.route("/<int:user_id>/deactivate", methods=["POST"])
@admin_required
def deactivate_user(user_id: int):
    user = User.query.get_or_404(user_id)
    user.is_active = False
    log_admin_action(
        current_user.id, "remove_user", "user", user.id,
        f"Removed user {user.email} ({user.full_name}).",
    )
    db.session.commit()
    flash(f"Removed {user.full_name}. They can no longer log in.", "info")
    return redirect(url_for("users.list_users"))


@bp.route("/<int:user_id>/activate", methods=["POST"])
@admin_required
def activate_user(user_id: int):
    user = User.query.get_or_404(user_id)
    user.is_active = True
    log_admin_action(
        current_user.id, "restore_user", "user", user.id,
        f"Restored user {user.email} ({user.full_name}).",
    )
    db.session.commit()
    flash(f"Restored {user.full_name}.", "success")
    return redirect(url_for("users.list_users"))


@bp.route("/<int:user_id>/reset-password", methods=["GET", "POST"])
@admin_required
def reset_password(user_id: int):
    user = User.query.get_or_404(user_id)
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        log_admin_action(
            current_user.id, "reset_password", "user", user.id,
            f"Reset password for {user.email}.",
        )
        db.session.commit()
        flash(f"Password reset for {user.email}.", "success")
        return redirect(url_for("users.list_users"))
    return render_template(
        "users/reset_password.html", form=form, user=user
    )


@bp.route("/export-csv")
@admin_required
def export_csv():
    """Download all users as a CSV file."""
    users = User.query.order_by(User.full_name).all()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for u in users:
        writer.writerow({
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role.value,
            "is_active": "yes" if u.is_active else "no",
            "is_voting_member": "yes" if u.is_voting_member else "no",
            "is_active_member": "yes" if u.is_active_member else "no",
            "family_group": u.family_group or "",
            "committees": u.committees or "",
            "password": "",  # Never export passwords.
        })
    log_admin_action(
        current_user.id, "export_users_csv", "user", None,
        f"Exported {len(users)} users to CSV.",
    )
    db.session.commit()
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=users.csv"
    return resp


@bp.route("/import-csv", methods=["GET", "POST"])
@admin_required
def import_csv():
    """Bulk create or update users from an uploaded CSV file."""
    form = CsvUploadForm()
    if form.validate_on_submit():
        file = form.csv_file.data
        try:
            stream = io.StringIO(file.read().decode("utf-8-sig"))
        except UnicodeDecodeError:
            flash("Could not read the file. Please upload a UTF-8 CSV.", "danger")
            return render_template("users/import_csv.html", form=form)

        reader = csv.DictReader(stream)
        # Validate header row.
        required_cols = {"email", "full_name", "role"}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            missing = required_cols - set(reader.fieldnames or [])
            flash(
                f"CSV is missing required columns: {', '.join(sorted(missing))}. "
                f"Required: email, full_name, role.",
                "danger",
            )
            return render_template("users/import_csv.html", form=form)

        results = {"created": [], "updated": [], "skipped": []}
        for row_num, row in enumerate(reader, start=2):
            email = (row.get("email") or "").strip().lower()
            full_name = (row.get("full_name") or "").strip()
            role_str = (row.get("role") or "").strip().lower()

            # --- Validate row ---
            if not email or not full_name:
                results["skipped"].append(
                    f"Row {row_num}: missing email or full_name."
                )
                continue
            if role_str not in VALID_ROLES:
                results["skipped"].append(
                    f"Row {row_num} ({email}): invalid role '{role_str}'. "
                    f"Valid: {', '.join(sorted(VALID_ROLES))}."
                )
                continue

            # --- Parse boolean fields (default to yes) ---
            def parse_bool(val: str, default: bool = True) -> bool:
                val = (val or "").strip().lower()
                if val in ("no", "false", "0", "n"):
                    return False
                if val in ("yes", "true", "1", "y", ""):
                    return default
                return default

            is_active = parse_bool(row.get("is_active", ""), True)
            is_voting = parse_bool(row.get("is_voting_member", ""), True)
            is_active_member = parse_bool(row.get("is_active_member", ""), True)
            family_group = (row.get("family_group") or "").strip() or None
            committees = (row.get("committees") or "").strip()
            password = (row.get("password") or "").strip()

            existing = User.query.filter_by(email=email).first()
            if existing:
                # --- Update existing user ---
                existing.full_name = full_name
                existing.role = Role(role_str)
                existing.is_active = is_active
                existing.is_voting_member = is_voting
                existing.is_active_member = is_active_member
                existing.family_group = family_group
                existing.committees = committees
                if password and len(password) >= 8:
                    existing.set_password(password)
                log_admin_action(
                    current_user.id, "csv_update_user", "user", existing.id,
                    f"Updated user {email} via CSV import.",
                )
                results["updated"].append(email)
            else:
                # --- Create new user ---
                if not password or len(password) < 8:
                    results["skipped"].append(
                        f"Row {row_num} ({email}): new user requires a "
                        f"password of at least 8 characters."
                    )
                    continue
                user = User(
                    email=email,
                    full_name=full_name,
                    role=Role(role_str),
                    is_active=is_active,
                    is_voting_member=is_voting,
                    is_active_member=is_active_member,
                    family_group=family_group,
                    committees=committees,
                )
                user.set_password(password)
                db.session.add(user)
                db.session.flush()
                log_admin_action(
                    current_user.id, "csv_create_user", "user", user.id,
                    f"Created user {email} via CSV import.",
                )
                results["created"].append(email)

        db.session.commit()

        total = len(results["created"]) + len(results["updated"])
        if total:
            flash(
                f"CSV import complete: {len(results['created'])} created, "
                f"{len(results['updated'])} updated.",
                "success",
            )
        if results["skipped"]:
            flash(
                f"{len(results['skipped'])} row(s) skipped. See details below.",
                "warning",
            )
        return render_template(
            "users/import_csv.html", form=CsvUploadForm(), results=results
        )

    return render_template("users/import_csv.html", form=form)


@bp.route("/admin-log")
@admin_required
def admin_log():
    page = request.args.get("page", 1, type=int)
    per_page = 50
    pagination = (
        AdminAction.query
        .order_by(AdminAction.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return render_template(
        "users/admin_log.html",
        actions=pagination.items,
        pagination=pagination,
    )


# ---------------------------------------------------------------------------
# Database backup & restore
# ---------------------------------------------------------------------------


def _get_db_path() -> Path | None:
    """Extract the SQLite file path from the database URI."""
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if "sqlite:///" not in uri:
        return None
    # sqlite:////absolute/path or sqlite:///relative/path
    raw = uri.split("sqlite:///", 1)[1]
    return Path(raw)


@bp.route("/backup-db")
@admin_required
def backup_db():
    """Download a copy of the SQLite database."""
    db_path = _get_db_path()
    if db_path is None or not db_path.exists():
        flash("Database backup is only available for SQLite databases.", "warning")
        return redirect(url_for("users.list_users"))
    stamp = now_eastern().strftime("%Y%m%d-%H%M%S")
    log_admin_action(
        current_user.id, "backup_database", "system", None,
        "Downloaded database backup.",
    )
    db.session.commit()
    return send_file(
        db_path,
        as_attachment=True,
        download_name=f"quorum-backup-{stamp}.db",
        mimetype="application/x-sqlite3",
    )


@bp.route("/restore-db", methods=["GET", "POST"])
@admin_required
def restore_db():
    """Upload a SQLite database to replace the current one."""
    if request.method == "POST":
        file = request.files.get("db_file")
        if not file or not file.filename:
            flash("No file selected.", "danger")
            return render_template("users/restore_db.html")

        db_path = _get_db_path()
        if db_path is None:
            flash("Database restore is only available for SQLite databases.", "warning")
            return redirect(url_for("users.list_users"))

        # Read uploaded file into memory.
        data = file.read()

        # Validate it looks like SQLite (magic header).
        if data[:16] != b"SQLite format 3\x00":
            flash("The uploaded file does not appear to be a valid SQLite database.", "danger")
            return render_template("users/restore_db.html")

        # Back up the current DB before replacing.
        stamp = now_eastern().strftime("%Y%m%d-%H%M%S")
        backup_path = db_path.parent / f"quorum-pre-restore-{stamp}.db"
        if db_path.exists():
            shutil.copy2(db_path, backup_path)

        # Close all connections, write the new file.
        db.session.remove()
        db.engine.dispose()
        db_path.write_bytes(data)

        flash(
            f"Database restored successfully. Previous database saved as {backup_path.name}. "
            "Please restart the application for changes to take full effect.",
            "success",
        )
        return redirect(url_for("users.list_users"))

    return render_template("users/restore_db.html")

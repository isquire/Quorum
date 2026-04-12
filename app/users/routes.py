from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..admin_log import log_admin_action
from ..extensions import db
from ..models import AdminAction, Role, User
from ..permissions import admin_required
from . import bp
from .forms import ResetPasswordForm, UserCreateForm, UserEditForm


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

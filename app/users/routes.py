from flask import flash, redirect, render_template, url_for

from ..extensions import db
from ..models import Role, User
from ..permissions import admin_required
from . import bp
from .forms import ResetPasswordForm, UserCreateForm, UserEditForm


@bp.route("/")
@admin_required
def list_users():
    users = User.query.order_by(User.full_name).all()
    return render_template("users/list.html", users=users)


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
                committees=(form.committees.data or "").strip(),
            )
            user.set_password(form.password.data)
            db.session.add(user)
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
        user.committees = (form.committees.data or "").strip()
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
    db.session.commit()
    flash(f"Deactivated {user.email}.", "info")
    return redirect(url_for("users.list_users"))


@bp.route("/<int:user_id>/activate", methods=["POST"])
@admin_required
def activate_user(user_id: int):
    user = User.query.get_or_404(user_id)
    user.is_active = True
    db.session.commit()
    flash(f"Activated {user.email}.", "success")
    return redirect(url_for("users.list_users"))


@bp.route("/<int:user_id>/reset-password", methods=["GET", "POST"])
@admin_required
def reset_password(user_id: int):
    user = User.query.get_or_404(user_id)
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(f"Password reset for {user.email}.", "success")
        return redirect(url_for("users.list_users"))
    return render_template(
        "users/reset_password.html", form=form, user=user
    )

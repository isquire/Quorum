from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional

from ..models import Role

ROLE_CHOICES = [
    (Role.admin.value, "Admin"),
    (Role.chair.value, "Chair"),
    (Role.vice_chair.value, "Vice-Chair"),
    (Role.secretary.value, "Secretary"),
    (Role.treasurer.value, "Treasurer"),
    (Role.member.value, "Member"),
]


class UserCreateForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    full_name = StringField("Full name", validators=[DataRequired()])
    role = SelectField("Role", choices=ROLE_CHOICES, validators=[DataRequired()])
    is_voting_member = BooleanField("Voting member", default=True)
    is_active = BooleanField("Active", default=True)
    is_active_member = BooleanField("Active member (counts toward quorum)", default=True)
    committees = StringField(
        "Committees (comma-separated)", validators=[Optional()]
    )
    password = PasswordField(
        "Temporary password",
        validators=[DataRequired(), Length(min=8)],
    )
    submit = SubmitField("Create user")


class UserEditForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    full_name = StringField("Full name", validators=[DataRequired()])
    role = SelectField("Role", choices=ROLE_CHOICES, validators=[DataRequired()])
    is_voting_member = BooleanField("Voting member")
    is_active = BooleanField("Active")
    is_active_member = BooleanField("Active member (counts toward quorum)")
    committees = StringField(
        "Committees (comma-separated)", validators=[Optional()]
    )
    submit = SubmitField("Save changes")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "New password", validators=[DataRequired(), Length(min=8)]
    )
    submit = SubmitField("Reset password")

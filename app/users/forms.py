from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional

from ..models import Role

ROLE_CHOICES = [
    (Role.admin.value, "Admin"),
    (Role.pastor.value, "Pastor"),
    (Role.deacon.value, "Deacon"),
    (Role.trustee.value, "Trustee"),
    (Role.secretary.value, "Secretary"),
    (Role.treasurer.value, "Treasurer"),
    (Role.assistant_treasurer.value, "Assistant Treasurer"),
    (Role.member.value, "Member"),
    # Legacy roles kept for backwards compat during migration.
    (Role.chair.value, "Chair (legacy)"),
    (Role.vice_chair.value, "Vice-Chair (legacy)"),
]


class UserCreateForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    full_name = StringField("Full name", validators=[DataRequired()])
    role = SelectField("Role", choices=ROLE_CHOICES, validators=[DataRequired()])
    is_voting_member = BooleanField("Voting member", default=True)
    is_active = BooleanField("Active", default=True)
    is_active_member = BooleanField("Active member (counts toward quorum)", default=True)
    family_group = StringField(
        "Family group", validators=[Optional()]
    )
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
    family_group = StringField(
        "Family group", validators=[Optional()]
    )
    committees = StringField(
        "Committees (comma-separated)", validators=[Optional()]
    )
    submit = SubmitField("Save changes")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "New password", validators=[DataRequired(), Length(min=8)]
    )
    submit = SubmitField("Reset password")

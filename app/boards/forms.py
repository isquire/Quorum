from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Optional

from ..models import BoardRole, TERM_RULES

# Only roles that have term limits.
TERM_TRACKED_ROLES = [
    (role, role.replace("_", " ").title())
    for role in TERM_RULES
]

ALL_BOARD_ROLES = [
    (r.value, r.value.replace("_", " ").title())
    for r in BoardRole
]

TERM_STATUS_CHOICES = [
    ("active", "Active (currently serving)"),
    ("completed", "Completed (past term, already ended)"),
]

TERM_END_STATUS_CHOICES = [
    ("resigned", "Resigned"),
    ("removed", "Removed"),
]


class BulkAddMembersForm(FlaskForm):
    """CSRF-only form; actual member rows come from request.form."""
    submit = SubmitField("Add selected members")


class BoardMembershipForm(FlaskForm):
    user_id = SelectField(
        "Member",
        choices=[],
        validators=[DataRequired()],
        coerce=int,
    )
    role_on_board = SelectField(
        "Role on board",
        choices=ALL_BOARD_ROLES,
        validators=[DataRequired()],
    )
    is_voting = BooleanField("Voting member", default=True)
    submit = SubmitField("Save")


class EditMembershipForm(FlaskForm):
    role_on_board = SelectField(
        "Role on board",
        choices=ALL_BOARD_ROLES,
        validators=[DataRequired()],
    )
    is_voting = BooleanField("Voting member", default=True)
    submit = SubmitField("Save")


class RecordTermForm(FlaskForm):
    user_id = SelectField(
        "Member",
        choices=[],
        validators=[DataRequired()],
        coerce=int,
    )
    role_on_board = SelectField(
        "Role",
        choices=TERM_TRACKED_ROLES,
        validators=[DataRequired()],
    )
    elected_at_meeting_id = SelectField(
        "Elected at meeting",
        choices=[],
        validators=[Optional()],
        coerce=int,
    )
    term_start = DateField(
        "Term start date",
        validators=[DataRequired()],
    )
    status = SelectField(
        "Status",
        choices=TERM_STATUS_CHOICES,
        validators=[DataRequired()],
    )
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Record term")


class EditTermForm(FlaskForm):
    term_start = DateField(
        "Term start date",
        validators=[DataRequired()],
    )
    term_end = DateField(
        "Term end date",
        validators=[DataRequired()],
    )
    status = SelectField(
        "Status",
        choices=[
            ("active", "Active"),
            ("completed", "Completed"),
            ("resigned", "Resigned"),
            ("removed", "Removed"),
        ],
        validators=[DataRequired()],
    )
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save changes")


class EndTermForm(FlaskForm):
    actual_end = DateField(
        "Last day of service",
        validators=[DataRequired()],
    )
    status = SelectField(
        "Reason",
        choices=TERM_END_STATUS_CHOICES,
        validators=[DataRequired()],
    )
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("End term")


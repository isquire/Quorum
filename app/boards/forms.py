from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Optional

from ..models import BoardRole, TERM_RULES

# Only roles that have term limits.
TERM_TRACKED_ROLES = [
    (role, role.replace("_", " ").title())
    for role in TERM_RULES
]

TERM_STATUS_CHOICES = [
    ("active", "Active (currently serving)"),
    ("completed", "Completed (past term, already ended)"),
]

TERM_END_STATUS_CHOICES = [
    ("resigned", "Resigned"),
    ("removed", "Removed"),
]


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


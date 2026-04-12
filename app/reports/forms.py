from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Optional

from ..models import ReportType

REPORT_TYPE_CHOICES = [
    (ReportType.treasurer.value, "Treasurer"),
    (ReportType.committee.value, "Committee"),
    (ReportType.pastor.value, "Pastor"),
    (ReportType.other.value, "Other"),
]


class ReportForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    report_type = SelectField(
        "Type", choices=REPORT_TYPE_CHOICES, validators=[DataRequired()]
    )
    committee = StringField("Committee", validators=[Optional()])
    period_start = DateField("Period start", validators=[Optional()])
    period_end = DateField("Period end", validators=[Optional()])
    content = TextAreaField("Content (markdown OK)", validators=[Optional()])
    meeting_id = SelectField(
        "Linked meeting", coerce=int, validators=[Optional()]
    )
    submit = SubmitField("Submit report")

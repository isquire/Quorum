from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateTimeLocalField,
    IntegerField,
    RadioField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, NumberRange, Optional

from ..models import (
    AgendaCategory,
    MajorityRule,
    MeetingType,
    MotionType,
    RsvpStatus,
    VoteChoice,
    VoteMethod,
)

MEETING_TYPE_CHOICES = [
    (MeetingType.regular.value, "Regular board meeting"),
    (MeetingType.special.value, "Special board meeting"),
    (MeetingType.annual.value, "Annual"),
    (MeetingType.emergency.value, "Emergency"),
    (MeetingType.annual_business.value, "Annual business (assembly)"),
    (MeetingType.special_business.value, "Special business (assembly)"),
]


class MeetingForm(FlaskForm):
    board_id = SelectField(
        "Board / body",
        choices=[],
        validators=[DataRequired()],
        coerce=int,
    )
    title = StringField("Title", validators=[DataRequired()])
    meeting_type = SelectField(
        "Type", choices=MEETING_TYPE_CHOICES, validators=[DataRequired()]
    )
    scheduled_start = DateTimeLocalField(
        "Start (local time)", format="%Y-%m-%dT%H:%M", validators=[DataRequired()]
    )
    scheduled_end = DateTimeLocalField(
        "End (optional)",
        format="%Y-%m-%dT%H:%M",
        validators=[Optional()],
    )
    location = StringField("Location / link", validators=[Optional()])
    # Bylaws Art I §2 — acting chair when the Pastor is absent.
    acting_chair_id = SelectField(
        "Acting chair (if Pastor unavailable)",
        choices=[],
        validators=[Optional()],
        coerce=int,
    )
    submit = SubmitField("Save meeting")


RSVP_CHOICES = [
    (RsvpStatus.yes.value, "Yes, attending"),
    (RsvpStatus.no.value, "No, cannot attend"),
    (RsvpStatus.maybe.value, "Maybe"),
]


class RsvpForm(FlaskForm):
    rsvp = RadioField(
        "RSVP", choices=RSVP_CHOICES, validators=[DataRequired()]
    )
    submit = SubmitField("Update RSVP")


AGENDA_CATEGORY_CHOICES = [
    (AgendaCategory.minutes_approval.value, "Approval of minutes"),
    (AgendaCategory.report.value, "Report"),
    (AgendaCategory.unfinished_business.value, "Unfinished business"),
    (AgendaCategory.new_business.value, "New business"),
    (AgendaCategory.announcement.value, "Announcement"),
]


class AgendaItemForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    category = SelectField(
        "Category",
        choices=AGENDA_CATEGORY_CHOICES,
        validators=[DataRequired()],
    )
    description = TextAreaField("Description", validators=[Optional()])
    presenter_id = SelectField(
        "Presenter", choices=[], validators=[Optional()], coerce=int
    )
    submit = SubmitField("Save")


MOTION_TYPE_CHOICES = [
    (MotionType.main.value, "Main motion"),
    (MotionType.amendment.value, "Amendment"),
    (MotionType.substitute_amendment.value, "Substitute amendment"),
    (MotionType.table.value, "Motion to table"),
    (MotionType.postpone.value, "Motion to postpone"),
    (MotionType.call_question.value, "Call the question"),
    (MotionType.adjourn.value, "Motion to adjourn"),
    (MotionType.recess.value, "Motion to recess"),
]


class MotionForm(FlaskForm):
    text = TextAreaField("Motion text", validators=[DataRequired()])
    motion_type = SelectField(
        "Type", choices=MOTION_TYPE_CHOICES, validators=[DataRequired()]
    )
    requires_majority = SelectField(
        "Majority",
        choices=[
            (MajorityRule.simple.value, "Simple majority"),
            (MajorityRule.two_thirds.value, "Two-thirds"),
        ],
        validators=[DataRequired()],
    )
    vote_method = SelectField(
        "Vote method",
        choices=[
            (VoteMethod.voice.value, "Voice / show-of-hands"),
            (VoteMethod.roll_call.value, "Roll call (per-member)"),
        ],
        validators=[DataRequired()],
    )
    # Constitution Art VIII §6 — only pastor and deacons vote.
    deacons_only = BooleanField(
        "Deacons-only vote (Board of Admin only)",
        default=False,
    )
    submit = SubmitField("Submit motion")


VOTE_CHOICES = [
    (VoteChoice.yes.value, "Yes"),
    (VoteChoice.no.value, "No"),
    (VoteChoice.abstain.value, "Abstain"),
]


class VoteForm(FlaskForm):
    choice = RadioField(
        "Vote", choices=VOTE_CHOICES, validators=[DataRequired()]
    )
    submit = SubmitField("Cast vote")


class ManualTallyForm(FlaskForm):
    """Chair enters yes/no/abstain counts for voice or show-of-hands votes."""
    yes_count = IntegerField(
        "Yes", validators=[DataRequired(), NumberRange(min=0)], default=0
    )
    no_count = IntegerField(
        "No", validators=[DataRequired(), NumberRange(min=0)], default=0
    )
    abstain_count = IntegerField(
        "Abstain", validators=[DataRequired(), NumberRange(min=0)], default=0
    )
    submit = SubmitField("Record tally")


class ChairNoteForm(FlaskForm):
    note = TextAreaField("Note", validators=[DataRequired()])
    submit = SubmitField("Add to minutes")

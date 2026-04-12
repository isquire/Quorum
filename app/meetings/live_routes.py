"""Live meeting controller — the chair's cockpit.

This is where the RRO state machine runs: motions are made, seconded,
amended, voted, and every action is auto-logged to the minutes timeline.
"""
from __future__ import annotations

from datetime import datetime

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from .. import minutes_logger
from ..extensions import db
from ..models import (
    BoardMembership,
    BoardRole,
    MajorityRule,
    Meeting,
    MeetingAttendance,
    MeetingStage,
    MeetingStatus,
    Motion,
    MotionStatus,
    MotionType,
    Role,
    User,
    Vote,
    VoteChoice,
    VoteMethod,
)
from ..permissions import CHAIR_ROLES, SECRETARY_ROLES, role_required, voting_member_required
from ..rro import (
    MAIN_MOTION_STAGES,
    available_motion_types,
    default_majority_rule,
    next_stage,
)
from .forms import ChairNoteForm, ManualTallyForm, MotionForm, VoteForm

bp = Blueprint("live", __name__, url_prefix="/meetings/<int:meeting_id>/live")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_meeting(meeting_id: int) -> Meeting:
    return Meeting.query.get_or_404(meeting_id)


def _is_acting_chair(meeting: Meeting) -> bool:
    """True if the current user is the meeting's acting chair."""
    return (
        meeting.acting_chair_id is not None
        and current_user.id == meeting.acting_chair_id
    )


def _require_chair_or_vice(meeting: Meeting) -> None:
    """Abort 403 unless the user holds a chair-equivalent role or is the
    acting chair for this meeting."""
    if _is_acting_chair(meeting):
        return
    if current_user.role.value not in CHAIR_ROLES:
        abort(403)


def _require_secretary_or_chair(meeting: Meeting) -> None:
    if _is_acting_chair(meeting):
        return
    if current_user.role.value not in SECRETARY_ROLES:
        abort(403)


def _active_motion(meeting: Meeting) -> Motion | None:
    """Return the innermost active motion (deepest amendment)."""
    motion = meeting.current_motion
    if motion is None:
        return None
    # Walk down to the innermost unresolved amendment, if any.
    while True:
        nested = [
            m
            for m in motion.amendments
            if m.status
            not in {
                MotionStatus.passed,
                MotionStatus.failed,
                MotionStatus.withdrawn,
            }
        ]
        if not nested:
            return motion
        motion = nested[0]


# ---------------------------------------------------------------------------
# Main live view
# ---------------------------------------------------------------------------


@bp.route("/", methods=["GET"])
@login_required
def live(meeting_id: int):
    meeting = _get_meeting(meeting_id)
    if meeting.status == MeetingStatus.cancelled:
        abort(404)

    active_motion = _active_motion(meeting)
    motion_form = MotionForm()
    vote_form = VoteForm()
    manual_tally_form = ManualTallyForm()
    note_form = ChairNoteForm()

    # Build list of allowed motion types for current state.
    allowed_types = available_motion_types(
        meeting.current_stage,
        active_motion is not None,
        meeting_type=meeting.meeting_type,
    )
    motion_form.motion_type.choices = [
        (t.value, t.value.replace("_", " ").title()) for t in allowed_types
    ]

    # Has the current user already voted on the active motion?
    my_vote = None
    if active_motion is not None:
        my_vote = Vote.query.filter_by(
            motion_id=active_motion.id, user_id=current_user.id
        ).first()

    is_chair = (
        current_user.role.value in CHAIR_ROLES
        or _is_acting_chair(meeting)
    )

    template = "meetings/live.html" if is_chair else "meetings/live_member.html"
    return render_template(
        template,
        meeting=meeting,
        active_motion=active_motion,
        motion_form=motion_form,
        vote_form=vote_form,
        manual_tally_form=manual_tally_form,
        note_form=note_form,
        my_vote=my_vote,
        allowed_motion_types=allowed_types,
        next_stage=next_stage(meeting.current_stage, meeting.meeting_type),
    )


# ---------------------------------------------------------------------------
# Stage management
# ---------------------------------------------------------------------------


@bp.route("/call-to-order", methods=["POST"])
@login_required
def call_to_order(meeting_id: int):
    meeting = _get_meeting(meeting_id)
    _require_chair_or_vice(meeting)

    if meeting.status != MeetingStatus.scheduled:
        flash("Meeting already started or ended.", "warning")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    meeting.status = MeetingStatus.in_progress
    # For annual-business meetings, the first stage is devotional, not call_to_order.
    from ..rro import stage_order_for
    stages = stage_order_for(meeting.meeting_type)
    first_stage = stages[1] if len(stages) > 1 else MeetingStage.call_to_order
    meeting.current_stage = first_stage
    meeting.called_to_order_at = datetime.utcnow()
    minutes_logger.log_call_to_order(meeting, current_user)
    db.session.commit()
    flash("Meeting called to order.", "success")
    return redirect(url_for("live.live", meeting_id=meeting_id))


@bp.route("/advance-stage", methods=["POST"])
@login_required
def advance_stage(meeting_id: int):
    meeting = _get_meeting(meeting_id)
    _require_chair_or_vice(meeting)
    if meeting.status != MeetingStatus.in_progress:
        flash("Meeting is not in progress.", "warning")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    nxt = next_stage(meeting.current_stage, meeting.meeting_type)
    if nxt is None:
        flash("Already at final stage.", "info")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    # Block stage advance while a motion is still on the floor in debate
    # stages.
    if meeting.current_motion_id is not None and meeting.current_stage in MAIN_MOTION_STAGES:
        flash(
            "A motion is still on the floor. Dispose of it before advancing.",
            "warning",
        )
        return redirect(url_for("live.live", meeting_id=meeting_id))

    meeting.current_stage = nxt
    minutes_logger.log_stage_change(meeting, nxt, current_user)
    db.session.commit()
    return redirect(url_for("live.live", meeting_id=meeting_id))


@bp.route("/set-agenda-item/<int:item_id>", methods=["POST"])
@login_required
def set_agenda_item(meeting_id: int, item_id: int):
    meeting = _get_meeting(meeting_id)
    _require_chair_or_vice(meeting)
    item = next(
        (i for i in meeting.agenda_items if i.id == item_id), None
    )
    if item is None:
        abort(404)
    meeting.current_agenda_item_id = item_id
    minutes_logger.log_agenda_item(meeting, item, current_user)
    db.session.commit()
    return redirect(url_for("live.live", meeting_id=meeting_id))


@bp.route("/adjourn", methods=["POST"])
@login_required
def adjourn(meeting_id: int):
    meeting = _get_meeting(meeting_id)
    _require_chair_or_vice(meeting)
    meeting.status = MeetingStatus.adjourned
    meeting.current_stage = MeetingStage.adjourned
    meeting.adjourned_at = datetime.utcnow()
    meeting.current_motion_id = None
    meeting.current_agenda_item_id = None
    minutes_logger.log_adjournment(meeting, current_user)
    db.session.commit()
    flash("Meeting adjourned.", "success")
    return redirect(url_for("meetings.meeting_detail", meeting_id=meeting_id))


# ---------------------------------------------------------------------------
# Attendance / roll call
# ---------------------------------------------------------------------------


@bp.route("/attendance/<int:user_id>/toggle", methods=["POST"])
@login_required
def toggle_attendance(meeting_id: int, user_id: int):
    meeting = _get_meeting(meeting_id)
    _require_secretary_or_chair(meeting)

    attendance = MeetingAttendance.query.filter_by(
        meeting_id=meeting_id, user_id=user_id
    ).first_or_404()
    user = User.query.get_or_404(user_id)

    attendance.is_present = not attendance.is_present
    if attendance.is_present and attendance.arrived_at is None:
        attendance.arrived_at = datetime.utcnow()
    minutes_logger.log_attendance(
        meeting, user, attendance.is_present, current_user
    )
    db.session.commit()
    return redirect(url_for("live.live", meeting_id=meeting_id))


@bp.route("/attendance/<int:user_id>/notify", methods=["POST"])
@login_required
def mark_notified(meeting_id: int, user_id: int):
    """Mark a board member as notified (Bylaws Art I §§2-3)."""
    meeting = _get_meeting(meeting_id)
    _require_secretary_or_chair(meeting)

    attendance = MeetingAttendance.query.filter_by(
        meeting_id=meeting_id, user_id=user_id
    ).first_or_404()

    if attendance.notified_at is None:
        attendance.notified_at = datetime.utcnow()
    else:
        # Toggle: clear the notified timestamp.
        attendance.notified_at = None

    db.session.commit()
    return redirect(url_for("live.live", meeting_id=meeting_id))


# ---------------------------------------------------------------------------
# Motions
# ---------------------------------------------------------------------------


@bp.route("/motions", methods=["POST"])
@voting_member_required
def make_motion(meeting_id: int):
    meeting = _get_meeting(meeting_id)
    if meeting.status != MeetingStatus.in_progress:
        flash("Meeting is not in session.", "warning")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    form = MotionForm()
    # Re-populate choices so WTForms validates.
    active = _active_motion(meeting)
    allowed = available_motion_types(
        meeting.current_stage,
        active is not None,
        meeting_type=meeting.meeting_type,
    )
    form.motion_type.choices = [
        (t.value, t.value) for t in allowed
    ]

    if not form.validate_on_submit():
        flash("Please fill in the motion text.", "danger")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    motion_type = MotionType(form.motion_type.data)
    if motion_type not in allowed:
        flash(f"A {motion_type.value} motion is not allowed right now.", "danger")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    motion = Motion(
        meeting_id=meeting.id,
        agenda_item_id=meeting.current_agenda_item_id,
        parent_motion_id=active.id if active and motion_type == MotionType.amendment else None,
        motion_type=motion_type,
        text=form.text.data.strip(),
        maker_id=current_user.id,
        status=MotionStatus.proposed,
        requires_majority=MajorityRule(form.requires_majority.data),
        vote_method=VoteMethod(form.vote_method.data),
        deacons_only=getattr(form, "deacons_only", None) and form.deacons_only.data or False,
    )
    # Two-thirds enforcement for certain motion types.
    default_rule = default_majority_rule(motion_type)
    if default_rule == MajorityRule.two_thirds:
        motion.requires_majority = MajorityRule.two_thirds

    db.session.add(motion)
    db.session.flush()

    if motion_type == MotionType.amendment and active is not None:
        minutes_logger.log_motion_amended(meeting, active, motion)
    else:
        minutes_logger.log_motion_made(meeting, motion)
        meeting.current_motion_id = motion.id

    db.session.commit()
    flash("Motion recorded. Awaiting a second.", "success")
    return redirect(url_for("live.live", meeting_id=meeting_id))


@bp.route("/motions/<int:motion_id>/second", methods=["POST"])
@voting_member_required
def second_motion(meeting_id: int, motion_id: int):
    meeting = _get_meeting(meeting_id)
    motion = Motion.query.get_or_404(motion_id)
    if motion.meeting_id != meeting.id:
        abort(404)
    if motion.status != MotionStatus.proposed:
        flash("Motion is not awaiting a second.", "warning")
        return redirect(url_for("live.live", meeting_id=meeting_id))
    if motion.maker_id == current_user.id:
        flash("You cannot second your own motion.", "danger")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    motion.seconder_id = current_user.id
    motion.status = MotionStatus.seconded
    db.session.flush()
    db.session.refresh(motion)
    minutes_logger.log_motion_seconded(meeting, motion)
    db.session.commit()
    flash("Motion seconded.", "success")
    return redirect(url_for("live.live", meeting_id=meeting_id))


@bp.route("/motions/<int:motion_id>/withdraw", methods=["POST"])
@login_required
def withdraw_motion(meeting_id: int, motion_id: int):
    meeting = _get_meeting(meeting_id)
    motion = Motion.query.get_or_404(motion_id)
    if motion.meeting_id != meeting.id:
        abort(404)
    if motion.maker_id != current_user.id and current_user.role != Role.admin:
        abort(403)
    if motion.status not in {MotionStatus.proposed, MotionStatus.seconded}:
        flash("Cannot withdraw a motion at this stage.", "warning")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    motion.status = MotionStatus.withdrawn
    if meeting.current_motion_id == motion.id:
        meeting.current_motion_id = motion.parent_motion_id
    minutes_logger.log_motion_withdrawn(meeting, motion)
    db.session.commit()
    flash("Motion withdrawn.", "info")
    return redirect(url_for("live.live", meeting_id=meeting_id))


@bp.route("/motions/<int:motion_id>/open-vote", methods=["POST"])
@login_required
def open_vote(meeting_id: int, motion_id: int):
    meeting = _get_meeting(meeting_id)
    _require_chair_or_vice(meeting)
    motion = Motion.query.get_or_404(motion_id)
    if motion.meeting_id != meeting.id:
        abort(404)
    if motion.status not in {MotionStatus.seconded, MotionStatus.debating}:
        flash("Motion must be seconded before voting.", "warning")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    motion.status = MotionStatus.voting
    db.session.commit()
    flash("Voting is now open.", "success")
    return redirect(url_for("live.live", meeting_id=meeting_id))


@bp.route("/motions/<int:motion_id>/vote", methods=["POST"])
@voting_member_required
def cast_vote(meeting_id: int, motion_id: int):
    meeting = _get_meeting(meeting_id)
    motion = Motion.query.get_or_404(motion_id)
    if motion.meeting_id != meeting.id:
        abort(404)
    if motion.status != MotionStatus.voting:
        flash("Voting is not open on this motion.", "warning")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    # Voice / show-of-hands votes use manual tally, not per-member votes.
    if motion.vote_method == VoteMethod.voice:
        flash("This motion uses voice / show-of-hands voting. The chair enters the tally.", "warning")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    # Constitution Art VIII §6 — deacons-only vote enforcement.
    if motion.deacons_only and meeting.board_id:
        membership = BoardMembership.query.filter_by(
            user_id=current_user.id, board_id=meeting.board_id
        ).first()
        if not membership or membership.role_on_board not in (
            BoardRole.pastor, BoardRole.deacon
        ):
            abort(403)

    form = VoteForm()
    if not form.validate_on_submit():
        flash("Invalid vote.", "danger")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    choice = VoteChoice(form.choice.data)
    existing = Vote.query.filter_by(
        motion_id=motion.id, user_id=current_user.id
    ).first()
    if existing is None:
        db.session.add(
            Vote(
                motion_id=motion.id,
                user_id=current_user.id,
                choice=choice,
                cast_at=datetime.utcnow(),
            )
        )
    else:
        existing.choice = choice
        existing.cast_at = datetime.utcnow()

    db.session.flush()
    motion.recount()
    db.session.commit()
    flash("Vote cast.", "success")
    return redirect(url_for("live.live", meeting_id=meeting_id))


@bp.route("/motions/<int:motion_id>/close-vote", methods=["POST"])
@login_required
def close_vote(meeting_id: int, motion_id: int):
    meeting = _get_meeting(meeting_id)
    _require_chair_or_vice(meeting)
    motion = Motion.query.get_or_404(motion_id)
    if motion.meeting_id != meeting.id:
        abort(404)
    if motion.status != MotionStatus.voting:
        flash("Motion is not in voting state.", "warning")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    # Only recount from Vote rows for roll-call votes.
    # Voice / show-of-hands tallies are already set via enter_manual_tally.
    if motion.vote_method == VoteMethod.roll_call:
        motion.recount()

    result = motion.compute_result()
    motion.result = result
    motion.status = (
        MotionStatus.passed if result.value == "passed" else MotionStatus.failed
    )
    motion.voted_at = datetime.utcnow()

    # If this motion was the current motion, pop back to its parent
    # (so amendments return control to the main motion).
    if meeting.current_motion_id == motion.id:
        meeting.current_motion_id = motion.parent_motion_id

    minutes_logger.log_motion_voted(meeting, motion, current_user)
    db.session.commit()
    flash(f"Vote closed: {result.value.upper()}.", "success")
    return redirect(url_for("live.live", meeting_id=meeting_id))


@bp.route("/motions/<int:motion_id>/manual-tally", methods=["POST"])
@login_required
def enter_manual_tally(meeting_id: int, motion_id: int):
    """Chair enters yes/no/abstain counts for voice or show-of-hands votes."""
    meeting = _get_meeting(meeting_id)
    _require_chair_or_vice(meeting)

    motion = Motion.query.get_or_404(motion_id)
    if motion.meeting_id != meeting.id:
        abort(404)
    if motion.status != MotionStatus.voting:
        flash("Motion is not in voting state.", "warning")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    form = ManualTallyForm()
    if not form.validate_on_submit():
        flash("Please enter valid vote counts.", "danger")
        return redirect(url_for("live.live", meeting_id=meeting_id))

    motion.yes_count = form.yes_count.data
    motion.no_count = form.no_count.data
    motion.abstain_count = form.abstain_count.data
    db.session.commit()
    flash("Tally recorded.", "success")
    return redirect(url_for("live.live", meeting_id=meeting_id))


# ---------------------------------------------------------------------------
# Free-form chair / secretary note
# ---------------------------------------------------------------------------


@bp.route("/note", methods=["POST"])
@login_required
def chair_note(meeting_id: int):
    meeting = _get_meeting(meeting_id)
    _require_secretary_or_chair(meeting)
    form = ChairNoteForm()
    if not form.validate_on_submit():
        flash("Please enter a note.", "danger")
        return redirect(url_for("live.live", meeting_id=meeting_id))
    minutes_logger.log_chair_note(meeting, form.note.data.strip(), current_user)
    db.session.commit()
    flash("Note added to minutes.", "success")
    return redirect(url_for("live.live", meeting_id=meeting_id))


# ---------------------------------------------------------------------------
# HTMX fragments
# ---------------------------------------------------------------------------


@bp.route("/fragment/<name>")
@login_required
def fragment(meeting_id: int, name: str):
    meeting = _get_meeting(meeting_id)
    if name == "quorum":
        return render_template(
            "meetings/_partials/quorum_badge.html", meeting=meeting
        )
    if name == "minutes":
        return render_template(
            "meetings/_partials/minutes_stream.html", meeting=meeting
        )
    if name == "motion":
        return render_template(
            "meetings/_partials/motion_card.html",
            meeting=meeting,
            active_motion=_active_motion(meeting),
        )
    abort(404)

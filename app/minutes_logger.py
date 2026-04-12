"""Centralized helpers that append MinutesEntry rows.

Every parliamentary action calls exactly one of these functions so the
minutes timeline always reflects reality.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func

from .extensions import db
from .models import (
    AgendaItem,
    Meeting,
    MeetingStage,
    MinutesEntry,
    MinutesEntryType,
    Motion,
    MotionResult,
    MotionType,
    User,
)
from .rro import MOTION_TYPE_LABELS, STAGE_LABELS


def _next_sequence(meeting_id: int) -> int:
    current_max = (
        db.session.query(func.max(MinutesEntry.sequence))
        .filter_by(meeting_id=meeting_id)
        .scalar()
    )
    return (current_max or 0) + 1


def _append(
    meeting: Meeting,
    entry_type: MinutesEntryType,
    text: str,
    actor: User | None = None,
    related_motion: Motion | None = None,
    related_agenda_item: AgendaItem | None = None,
) -> MinutesEntry:
    entry = MinutesEntry(
        meeting_id=meeting.id,
        sequence=_next_sequence(meeting.id),
        timestamp=datetime.utcnow(),
        entry_type=entry_type,
        actor_id=actor.id if actor else None,
        related_motion_id=related_motion.id if related_motion else None,
        related_agenda_item_id=(
            related_agenda_item.id if related_agenda_item else None
        ),
        text=text,
    )
    db.session.add(entry)
    return entry


# ---------------------------------------------------------------------------
# Public logging helpers
# ---------------------------------------------------------------------------


def log_call_to_order(meeting: Meeting, actor: User) -> MinutesEntry:
    time_str = datetime.utcnow().strftime("%H:%M UTC")
    return _append(
        meeting,
        MinutesEntryType.stage_change,
        f"{actor.full_name} called the meeting to order at {time_str}.",
        actor=actor,
    )


def log_stage_change(
    meeting: Meeting, new_stage: MeetingStage, actor: User
) -> MinutesEntry:
    return _append(
        meeting,
        MinutesEntryType.stage_change,
        f"Proceeded to: {STAGE_LABELS[new_stage]}.",
        actor=actor,
    )


def log_attendance(
    meeting: Meeting, member: User, is_present: bool, actor: User
) -> MinutesEntry:
    state = "present" if is_present else "absent"
    return _append(
        meeting,
        MinutesEntryType.attendance,
        f"{member.full_name} marked {state}.",
        actor=actor,
    )


def log_agenda_item(
    meeting: Meeting, item: AgendaItem, actor: User
) -> MinutesEntry:
    return _append(
        meeting,
        MinutesEntryType.agenda_item,
        f'Agenda item taken up: "{item.title}".',
        actor=actor,
        related_agenda_item=item,
    )


def log_motion_made(meeting: Meeting, motion: Motion) -> MinutesEntry:
    label = MOTION_TYPE_LABELS.get(motion.motion_type, motion.motion_type.value)
    text = (
        f"{motion.maker.full_name} made a {label.lower()}: "
        f'"{motion.text}".'
    )
    return _append(
        meeting,
        MinutesEntryType.motion_made,
        text,
        actor=motion.maker,
        related_motion=motion,
    )


def log_motion_seconded(meeting: Meeting, motion: Motion) -> MinutesEntry:
    return _append(
        meeting,
        MinutesEntryType.motion_seconded,
        f"{motion.seconder.full_name} seconded the motion.",
        actor=motion.seconder,
        related_motion=motion,
    )


def log_motion_amended(
    meeting: Meeting, parent: Motion, amendment: Motion
) -> MinutesEntry:
    return _append(
        meeting,
        MinutesEntryType.motion_amended,
        (
            f"{amendment.maker.full_name} proposed an amendment: "
            f'"{amendment.text}".'
        ),
        actor=amendment.maker,
        related_motion=amendment,
    )


def log_motion_withdrawn(meeting: Meeting, motion: Motion) -> MinutesEntry:
    return _append(
        meeting,
        MinutesEntryType.motion_withdrawn,
        f"{motion.maker.full_name} withdrew the motion.",
        actor=motion.maker,
        related_motion=motion,
    )


def log_motion_voted(
    meeting: Meeting, motion: Motion, actor: User
) -> MinutesEntry:
    verdict = "PASSED" if motion.result == MotionResult.passed else "FAILED"
    tally = (
        f"{motion.yes_count} yes, {motion.no_count} no, "
        f"{motion.abstain_count} abstain"
    )
    text = (
        f'Vote on motion: "{motion.text}" — {verdict} ({tally}).'
    )
    return _append(
        meeting,
        MinutesEntryType.motion_voted,
        text,
        actor=actor,
        related_motion=motion,
    )


def log_chair_note(meeting: Meeting, note: str, actor: User) -> MinutesEntry:
    return _append(
        meeting,
        MinutesEntryType.chair_note,
        note,
        actor=actor,
    )


def log_adjournment(meeting: Meeting, actor: User) -> MinutesEntry:
    time_str = datetime.utcnow().strftime("%H:%M UTC")
    return _append(
        meeting,
        MinutesEntryType.adjournment,
        f"{actor.full_name} declared the meeting adjourned at {time_str}.",
        actor=actor,
    )

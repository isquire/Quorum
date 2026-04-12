"""Robert's Rules of Order state machine and helpers.

Single source of truth for:
- allowed stage transitions in the standard order of business
- which motion types are legal at a given stage
- the default majority rule per motion type
- human-readable labels for the UI
"""
from __future__ import annotations

from .models import MajorityRule, MeetingStage, MotionType

STAGE_ORDER: list[MeetingStage] = [
    MeetingStage.not_started,
    MeetingStage.call_to_order,
    MeetingStage.roll_call,
    MeetingStage.minutes_approval,
    MeetingStage.reports,
    MeetingStage.unfinished_business,
    MeetingStage.new_business,
    MeetingStage.announcements,
    MeetingStage.adjourned,
]

STAGE_LABELS: dict[MeetingStage, str] = {
    MeetingStage.not_started: "Not started",
    MeetingStage.call_to_order: "Call to order",
    MeetingStage.roll_call: "Roll call / attendance",
    MeetingStage.minutes_approval: "Approval of previous minutes",
    MeetingStage.reports: "Reports of officers and committees",
    MeetingStage.unfinished_business: "Unfinished business",
    MeetingStage.new_business: "New business",
    MeetingStage.announcements: "Announcements",
    MeetingStage.adjourned: "Adjourned",
}

MOTION_TYPE_LABELS: dict[MotionType, str] = {
    MotionType.main: "Main motion",
    MotionType.amendment: "Amendment",
    MotionType.substitute_amendment: "Substitute amendment",
    MotionType.table: "Motion to table",
    MotionType.postpone: "Motion to postpone",
    MotionType.call_question: "Call the question (end debate)",
    MotionType.adjourn: "Motion to adjourn",
    MotionType.recess: "Motion to recess",
    MotionType.point_of_order: "Point of order",
}

# Motions that require a two-thirds majority (RRO).
TWO_THIRDS_MOTIONS: set[MotionType] = {
    MotionType.call_question,  # ending debate
}

# Stages at which main motions are appropriate. Subsidiary motions (amend,
# table, postpone, call question, recess, adjourn) are always available
# while another motion is on the floor.
MAIN_MOTION_STAGES: set[MeetingStage] = {
    MeetingStage.reports,
    MeetingStage.unfinished_business,
    MeetingStage.new_business,
}


def next_stage(current: MeetingStage) -> MeetingStage | None:
    """Return the next stage in the standard RRO order of business."""
    try:
        idx = STAGE_ORDER.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(STAGE_ORDER):
        return None
    return STAGE_ORDER[idx + 1]


def can_advance(current: MeetingStage) -> bool:
    return next_stage(current) is not None


def available_motion_types(
    current_stage: MeetingStage, has_active_motion: bool
) -> list[MotionType]:
    """Return motion types that are legal at the current point."""
    if current_stage == MeetingStage.adjourned:
        return []

    # Procedural motions that are always available once the meeting has
    # been called to order.
    procedural = [
        MotionType.recess,
        MotionType.adjourn,
        MotionType.point_of_order,
    ]

    if has_active_motion:
        # Subsidiary motions that modify or dispose of the active motion.
        return [
            MotionType.amendment,
            MotionType.substitute_amendment,
            MotionType.table,
            MotionType.postpone,
            MotionType.call_question,
        ] + procedural

    if current_stage in MAIN_MOTION_STAGES:
        return [MotionType.main] + procedural

    # Stages like call_to_order, roll_call, minutes_approval,
    # announcements — only procedural motions.
    return procedural


def default_majority_rule(motion_type: MotionType) -> MajorityRule:
    if motion_type in TWO_THIRDS_MOTIONS:
        return MajorityRule.two_thirds
    return MajorityRule.simple

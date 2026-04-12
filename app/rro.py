"""Robert's Rules of Order state machine and helpers.

Single source of truth for:
- allowed stage transitions in the standard order of business
- the annual-business assembly stage sequence (Bylaws Art VII)
- which motion types are legal at a given stage
- the default majority rule per motion type
- human-readable labels for the UI
"""
from __future__ import annotations

from .models import MajorityRule, MeetingStage, MeetingType, MotionType

# ---------------------------------------------------------------------------
# Stage sequences
# ---------------------------------------------------------------------------

# Default RRO order of business (board meetings, special business, emergency).
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

# Annual-business assembly meeting (Bylaws Art VII).
ANNUAL_BUSINESS_STAGES: list[MeetingStage] = [
    MeetingStage.not_started,
    MeetingStage.devotional,
    MeetingStage.minutes_reading,
    MeetingStage.treasurer_report,
    MeetingStage.committee_reports,
    MeetingStage.unfinished_business,
    MeetingStage.elections,
    MeetingStage.new_business,
    MeetingStage.adjournment,
]


def stage_order_for(meeting_type: MeetingType) -> list[MeetingStage]:
    """Return the stage sequence for a given meeting type."""
    if meeting_type == MeetingType.annual_business:
        return ANNUAL_BUSINESS_STAGES
    return STAGE_ORDER


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

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
    # Annual-business stages
    MeetingStage.devotional: "Devotional",
    MeetingStage.minutes_reading: "Reading of previous minutes",
    MeetingStage.treasurer_report: "Report of treasurer",
    MeetingStage.committee_reports: "Report of committees",
    MeetingStage.elections: "Election of officers",
    MeetingStage.adjournment: "Adjournment",
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
    # Supermajority types (Bylaws)
    MotionType.bylaw_amendment: "Bylaw amendment (2/3 required)",
    MotionType.property_transfer: "Property transfer (2/3 required)",
    MotionType.pastor_election: "Pastor election (2/3 required)",
}

# ---------------------------------------------------------------------------
# Majority rules
# ---------------------------------------------------------------------------

# Motions that require a two-thirds majority.
TWO_THIRDS_MOTIONS: set[MotionType] = {
    MotionType.call_question,       # RRO: ending debate
    MotionType.bylaw_amendment,     # Bylaws Art IX
    MotionType.property_transfer,   # Bylaws Art VI §2
    MotionType.pastor_election,     # Bylaws Art II §1
}

# ---------------------------------------------------------------------------
# Main-motion stages (where new substantive motions are in order)
# ---------------------------------------------------------------------------

# Stages at which main motions are appropriate. Subsidiary motions (amend,
# table, postpone, call question, recess, adjourn) are always available
# while another motion is on the floor.
MAIN_MOTION_STAGES: set[MeetingStage] = {
    MeetingStage.reports,
    MeetingStage.unfinished_business,
    MeetingStage.new_business,
    # Annual-business stages where motions are in order
    MeetingStage.treasurer_report,
    MeetingStage.committee_reports,
    MeetingStage.elections,
}

# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------


def next_stage(
    current: MeetingStage,
    meeting_type: MeetingType | None = None,
) -> MeetingStage | None:
    """Return the next stage in the appropriate order of business."""
    order = stage_order_for(meeting_type) if meeting_type else STAGE_ORDER
    try:
        idx = order.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(order):
        return None
    return order[idx + 1]


def can_advance(
    current: MeetingStage,
    meeting_type: MeetingType | None = None,
) -> bool:
    return next_stage(current, meeting_type) is not None


def available_motion_types(
    current_stage: MeetingStage,
    has_active_motion: bool,
    meeting_type: MeetingType | None = None,
) -> list[MotionType]:
    """Return motion types that are legal at the current point."""
    terminal = {MeetingStage.adjourned, MeetingStage.adjournment}
    if current_stage in terminal:
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
        result = [MotionType.main]
        # Supermajority motion types only available at assembly meetings.
        if meeting_type in {MeetingType.annual_business, MeetingType.special_business}:
            result.extend([
                MotionType.bylaw_amendment,
                MotionType.property_transfer,
                MotionType.pastor_election,
            ])
        return result + procedural

    # Stages like call_to_order, roll_call, minutes_approval,
    # announcements — only procedural motions.
    return procedural


def default_majority_rule(motion_type: MotionType) -> MajorityRule:
    if motion_type in TWO_THIRDS_MOTIONS:
        return MajorityRule.two_thirds
    return MajorityRule.simple

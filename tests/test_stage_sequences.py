"""Tests for meeting stage sequences.

Bylaws Art VII defines a custom order of business for the annual assembly
meeting. All other meeting types use the default RRO stage order.
"""
from app.models import MeetingStage, MeetingType
from app.rro import (
    ANNUAL_BUSINESS_STAGES,
    STAGE_ORDER,
    next_stage,
    stage_order_for,
)


def test_default_rro_stage_order(app):
    """Board meetings / special / emergency use the standard RRO flow."""
    order = stage_order_for(MeetingType.regular)
    assert order == STAGE_ORDER
    assert order[0] == MeetingStage.not_started
    assert order[1] == MeetingStage.call_to_order
    assert order[-1] == MeetingStage.adjourned


def test_annual_business_stage_order(app):
    """Annual-business assembly uses the Bylaws Art VII sequence."""
    order = stage_order_for(MeetingType.annual_business)
    assert order == ANNUAL_BUSINESS_STAGES
    assert order[0] == MeetingStage.not_started
    assert order[1] == MeetingStage.devotional
    assert order[2] == MeetingStage.minutes_reading
    assert order[3] == MeetingStage.treasurer_report
    assert order[4] == MeetingStage.committee_reports
    assert order[5] == MeetingStage.unfinished_business
    assert order[6] == MeetingStage.elections
    assert order[7] == MeetingStage.new_business
    assert order[8] == MeetingStage.adjournment


def test_special_business_uses_default(app):
    """Special-business meetings use the default RRO flow, not the annual one."""
    order = stage_order_for(MeetingType.special_business)
    assert order == STAGE_ORDER


def test_next_stage_advances_default(app):
    """next_stage with no meeting_type uses default RRO flow."""
    assert next_stage(MeetingStage.not_started) == MeetingStage.call_to_order
    assert next_stage(MeetingStage.call_to_order) == MeetingStage.roll_call
    assert next_stage(MeetingStage.announcements) == MeetingStage.adjourned
    assert next_stage(MeetingStage.adjourned) is None


def test_next_stage_annual_business(app):
    """next_stage for annual_business follows the Bylaws Art VII sequence."""
    mt = MeetingType.annual_business
    assert next_stage(MeetingStage.not_started, mt) == MeetingStage.devotional
    assert next_stage(MeetingStage.devotional, mt) == MeetingStage.minutes_reading
    assert next_stage(MeetingStage.minutes_reading, mt) == MeetingStage.treasurer_report
    assert next_stage(MeetingStage.treasurer_report, mt) == MeetingStage.committee_reports
    assert next_stage(MeetingStage.committee_reports, mt) == MeetingStage.unfinished_business
    assert next_stage(MeetingStage.unfinished_business, mt) == MeetingStage.elections
    assert next_stage(MeetingStage.elections, mt) == MeetingStage.new_business
    assert next_stage(MeetingStage.new_business, mt) == MeetingStage.adjournment
    assert next_stage(MeetingStage.adjournment, mt) is None


def test_full_walkthrough_annual_no_gaps(app):
    """Walking the full annual-business sequence from start to finish."""
    stage = MeetingStage.not_started
    visited = [stage]
    mt = MeetingType.annual_business
    while True:
        nxt = next_stage(stage, mt)
        if nxt is None:
            break
        visited.append(nxt)
        stage = nxt
    assert visited == ANNUAL_BUSINESS_STAGES


def test_full_walkthrough_default_no_gaps(app):
    """Walking the full default RRO sequence from start to finish."""
    stage = MeetingStage.not_started
    visited = [stage]
    while True:
        nxt = next_stage(stage)
        if nxt is None:
            break
        visited.append(nxt)
        stage = nxt
    assert visited == STAGE_ORDER

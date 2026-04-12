"""Tests for supermajority (two-thirds) motion types.

Bylaws Art IX (bylaw amendments), Art VI §2 (property transfer),
Art II §1 (pastor election) all require a 2/3 majority.
"""
from app.models import (
    MajorityRule,
    Motion,
    MotionResult,
    MotionStatus,
    MotionType,
)
from app.rro import TWO_THIRDS_MOTIONS, default_majority_rule


def test_bylaw_amendment_requires_two_thirds(app):
    """bylaw_amendment motion auto-sets two-thirds majority."""
    assert MotionType.bylaw_amendment in TWO_THIRDS_MOTIONS
    assert default_majority_rule(MotionType.bylaw_amendment) == MajorityRule.two_thirds


def test_property_transfer_requires_two_thirds(app):
    assert MotionType.property_transfer in TWO_THIRDS_MOTIONS
    assert default_majority_rule(MotionType.property_transfer) == MajorityRule.two_thirds


def test_pastor_election_requires_two_thirds(app):
    assert MotionType.pastor_election in TWO_THIRDS_MOTIONS
    assert default_majority_rule(MotionType.pastor_election) == MajorityRule.two_thirds


def test_two_thirds_passes_at_threshold(app):
    """4 yes / 2 no = 66.6% — exactly meets 2/3."""
    m = Motion(
        meeting_id=1,
        motion_type=MotionType.bylaw_amendment,
        text="Amend bylaws",
        maker_id=1,
        status=MotionStatus.voting,
        requires_majority=MajorityRule.two_thirds,
        yes_count=4,
        no_count=2,
        abstain_count=1,
    )
    assert m.compute_result() == MotionResult.passed


def test_two_thirds_fails_below_threshold(app):
    """3 yes / 2 no / 2 abstain — 60%, below 2/3."""
    m = Motion(
        meeting_id=1,
        motion_type=MotionType.bylaw_amendment,
        text="Amend bylaws",
        maker_id=1,
        status=MotionStatus.voting,
        requires_majority=MajorityRule.two_thirds,
        yes_count=3,
        no_count=2,
        abstain_count=2,
    )
    assert m.compute_result() == MotionResult.failed


def test_two_thirds_edge_exact_boundary(app):
    """2 yes / 1 no — 66.6%, exactly 2/3."""
    m = Motion(
        meeting_id=1,
        motion_type=MotionType.property_transfer,
        text="Transfer property",
        maker_id=1,
        status=MotionStatus.voting,
        requires_majority=MajorityRule.two_thirds,
        yes_count=2,
        no_count=1,
        abstain_count=0,
    )
    assert m.compute_result() == MotionResult.passed


def test_simple_majority_still_works(app):
    """Regular main motions still use simple majority."""
    assert default_majority_rule(MotionType.main) == MajorityRule.simple
    m = Motion(
        meeting_id=1,
        motion_type=MotionType.main,
        text="Regular motion",
        maker_id=1,
        status=MotionStatus.voting,
        requires_majority=MajorityRule.simple,
        yes_count=3,
        no_count=2,
        abstain_count=0,
    )
    assert m.compute_result() == MotionResult.passed

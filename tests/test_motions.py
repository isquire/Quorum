"""Tests for the core motion lifecycle and Robert's Rules logic."""
from datetime import datetime

from app.extensions import db
from app.models import (
    MajorityRule,
    Meeting,
    MeetingStage,
    MeetingStatus,
    Motion,
    MotionResult,
    MotionStatus,
    MotionType,
    User,
    Vote,
    VoteChoice,
)


def _start_meeting(meeting: Meeting, chair: User):
    meeting.status = MeetingStatus.in_progress
    meeting.current_stage = MeetingStage.new_business
    meeting.called_to_order_at = datetime.utcnow()
    db.session.commit()


def test_propose_and_second_lifecycle(client, chair, members, meeting, auth):
    _start_meeting(meeting, chair)

    # Mark all voting members present
    for a in meeting.attendances:
        a.is_present = True
    db.session.commit()

    # Member 1 proposes a motion
    auth.login("member1@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions",
        data={
            "text": "I move to approve the new sound system for $4500.",
            "motion_type": "main",
            "requires_majority": "simple",
            "vote_method": "voice",
            "submit": "Submit motion",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    motion = Motion.query.one()
    assert motion.status == MotionStatus.proposed

    # Maker cannot second own motion
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/second",
        follow_redirects=True,
    )
    assert b"cannot second your own" in resp.data

    # Member 2 seconds
    auth.logout()
    auth.login("member2@example.com")
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/second",
        follow_redirects=True,
    )
    db.session.refresh(motion)
    assert motion.status == MotionStatus.seconded
    assert motion.seconder.email == "member2@example.com"


def test_vote_lifecycle_simple_majority(client, chair, members, meeting, auth):
    _start_meeting(meeting, chair)
    for a in meeting.attendances:
        a.is_present = True
    db.session.commit()

    # Create a motion that has been seconded (directly via DB for brevity)
    m1 = User.query.filter_by(email="member1@example.com").one()
    m2 = User.query.filter_by(email="member2@example.com").one()
    motion = Motion(
        meeting_id=meeting.id,
        motion_type=MotionType.main,
        text="Test motion",
        maker_id=m1.id,
        seconder_id=m2.id,
        status=MotionStatus.seconded,
        requires_majority=MajorityRule.simple,
    )
    db.session.add(motion)
    db.session.flush()
    meeting.current_motion_id = motion.id
    db.session.commit()

    # Chair opens vote
    auth.login("chair@example.com")
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/open-vote",
        follow_redirects=True,
    )
    db.session.refresh(motion)
    assert motion.status == MotionStatus.voting

    # Three members vote yes, one no, one abstain
    for email, choice in [
        ("member1@example.com", "yes"),
        ("member2@example.com", "yes"),
        ("member3@example.com", "yes"),
        ("member4@example.com", "no"),
        ("member5@example.com", "abstain"),
    ]:
        auth.logout()
        auth.login(email)
        client.post(
            f"/meetings/{meeting.id}/live/motions/{motion.id}/vote",
            data={"choice": choice, "submit": "Cast vote"},
            follow_redirects=True,
        )

    # Chair closes vote
    auth.logout()
    auth.login("chair@example.com")
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/close-vote",
        follow_redirects=True,
    )
    db.session.refresh(motion)
    assert motion.result == MotionResult.passed
    assert motion.yes_count == 3
    assert motion.no_count == 1
    assert motion.abstain_count == 1


def test_two_thirds_majority_calculation(app):
    m = Motion(
        meeting_id=1,
        motion_type=MotionType.call_question,
        text="call the question",
        maker_id=1,
        status=MotionStatus.voting,
        requires_majority=MajorityRule.two_thirds,
        yes_count=4,
        no_count=2,
        abstain_count=0,
    )
    # 4 of 6 non-abstaining = 66.6% → exactly 2/3 passes
    assert m.compute_result() == MotionResult.passed

    m.yes_count = 3
    m.no_count = 3
    assert m.compute_result() == MotionResult.failed

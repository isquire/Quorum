"""Tests for the secretary-driven meeting workflow.

The secretary can operate the entire live meeting from a single device:
make motions, second, and record votes on behalf of members.
"""
from datetime import datetime

from app.extensions import db
from app.models import (
    MajorityRule,
    Meeting,
    MeetingStage,
    MeetingStatus,
    MinutesEntry,
    MinutesEntryType,
    Motion,
    MotionResult,
    MotionStatus,
    MotionType,
    Role,
    User,
    Vote,
    VoteChoice,
    VoteMethod,
)


def _start_meeting(meeting: Meeting):
    meeting.status = MeetingStatus.in_progress
    meeting.current_stage = MeetingStage.new_business
    meeting.called_to_order_at = datetime.utcnow()
    for a in meeting.attendances:
        a.is_present = True
    db.session.commit()


def _seconded_motion(meeting, maker, seconder):
    motion = Motion(
        meeting_id=meeting.id,
        motion_type=MotionType.main,
        text="Test motion",
        maker_id=maker.id,
        seconder_id=seconder.id,
        status=MotionStatus.seconded,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.roll_call,
    )
    db.session.add(motion)
    db.session.flush()
    meeting.current_motion_id = motion.id
    db.session.commit()
    return motion


# ---------------------------------------------------------------------------
# Secretary sees the officer view
# ---------------------------------------------------------------------------


def test_secretary_sees_officer_view(client, secretary, meeting, auth):
    """Secretary should see the full meeting controls, not the member view."""
    _start_meeting(meeting)
    auth.login("sec@example.com")
    resp = client.get(f"/meetings/{meeting.id}/live/")
    assert resp.status_code == 200
    assert b"Meeting controls" in resp.data
    assert b"Attendance (roll call)" in resp.data


def test_member_sees_member_view(client, members, meeting, auth):
    """Regular member should see the simplified member view."""
    _start_meeting(meeting)
    auth.login("member1@example.com")
    resp = client.get(f"/meetings/{meeting.id}/live/")
    assert resp.status_code == 200
    assert b"Meeting controls" not in resp.data


# ---------------------------------------------------------------------------
# Secretary stage management
# ---------------------------------------------------------------------------


def test_secretary_can_call_to_order(client, secretary, members, meeting, auth):
    auth.login("sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/call-to-order",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(meeting)
    assert meeting.status == MeetingStatus.in_progress


def test_secretary_can_advance_stage(client, secretary, members, meeting, auth):
    _start_meeting(meeting)
    auth.login("sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/advance-stage",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(meeting)
    assert meeting.current_stage != MeetingStage.new_business


def test_secretary_can_adjourn(client, secretary, members, meeting, auth):
    _start_meeting(meeting)
    auth.login("sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/adjourn",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(meeting)
    assert meeting.status == MeetingStatus.adjourned


def test_member_cannot_advance_stage(client, members, meeting, auth):
    _start_meeting(meeting)
    auth.login("member1@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/advance-stage",
        follow_redirects=False,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Motion on behalf
# ---------------------------------------------------------------------------


def test_secretary_makes_motion_on_behalf(client, secretary, members, meeting, auth):
    _start_meeting(meeting)
    member = User.query.filter_by(email="member1@example.com").one()
    auth.login("sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions",
        data={
            "text": "Motion from member 1 via secretary",
            "motion_type": "main",
            "requires_majority": "simple",
            "vote_method": "roll_call",
            "maker_id": str(member.id),
            "submit": "Submit motion",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    motion = Motion.query.one()
    assert motion.maker_id == member.id
    assert motion.text == "Motion from member 1 via secretary"

    # Minutes should attribute the motion to the actual member.
    entry = MinutesEntry.query.filter_by(
        entry_type=MinutesEntryType.motion_made
    ).first()
    assert entry is not None
    assert "Member 1" in entry.text


def test_secretary_makes_motion_as_self_if_voting(client, make_user, members, meeting, auth, db):
    """Secretary who is also a voting member can make motions as themselves."""
    sec = make_user(
        email="sec_voter@example.com",
        full_name="Secretary Voter",
        role=Role.secretary,
        is_voting_member=True,
    )
    db.session.add(
        __import__("app.models", fromlist=["MeetingAttendance"]).MeetingAttendance(
            meeting_id=meeting.id, user_id=sec.id, is_present=True,
        )
    )
    db.session.commit()
    _start_meeting(meeting)

    auth.login("sec_voter@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions",
        data={
            "text": "Secretary's own motion",
            "motion_type": "main",
            "requires_majority": "simple",
            "vote_method": "voice",
            "maker_id": "0",
            "submit": "Submit motion",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    motion = Motion.query.one()
    assert motion.maker_id == sec.id


def test_secretary_must_select_maker_if_not_voting(client, secretary, members, meeting, auth):
    """Non-voting secretary must select a member to make the motion."""
    secretary.is_voting_member = False
    db.session.commit()
    _start_meeting(meeting)

    auth.login("sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions",
        data={
            "text": "No maker selected",
            "motion_type": "main",
            "requires_majority": "simple",
            "vote_method": "voice",
            "maker_id": "0",
            "submit": "Submit motion",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"select a member" in resp.data.lower()
    assert Motion.query.count() == 0


def test_regular_member_makes_motion_normally(client, members, meeting, auth):
    """Regular voting members can still make motions as themselves."""
    _start_meeting(meeting)
    auth.login("member1@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions",
        data={
            "text": "Member's own motion",
            "motion_type": "main",
            "requires_majority": "simple",
            "vote_method": "voice",
            "maker_id": "0",
            "submit": "Submit motion",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    motion = Motion.query.one()
    member = User.query.filter_by(email="member1@example.com").one()
    assert motion.maker_id == member.id


# ---------------------------------------------------------------------------
# Second on behalf
# ---------------------------------------------------------------------------


def test_secretary_seconds_on_behalf(client, secretary, members, meeting, auth):
    _start_meeting(meeting)
    m1 = User.query.filter_by(email="member1@example.com").one()
    m2 = User.query.filter_by(email="member2@example.com").one()

    # Create a proposed motion.
    motion = Motion(
        meeting_id=meeting.id,
        motion_type=MotionType.main,
        text="Needs a second",
        maker_id=m1.id,
        status=MotionStatus.proposed,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.roll_call,
    )
    db.session.add(motion)
    db.session.flush()
    meeting.current_motion_id = motion.id
    db.session.commit()

    auth.login("sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/second",
        data={"seconder_id": str(m2.id)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(motion)
    assert motion.seconder_id == m2.id
    assert motion.status == MotionStatus.seconded


def test_secretary_cannot_second_as_maker(client, secretary, members, meeting, auth):
    """Secretary can't select the motion maker as the seconder."""
    _start_meeting(meeting)
    m1 = User.query.filter_by(email="member1@example.com").one()

    motion = Motion(
        meeting_id=meeting.id,
        motion_type=MotionType.main,
        text="Needs a second",
        maker_id=m1.id,
        status=MotionStatus.proposed,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.roll_call,
    )
    db.session.add(motion)
    db.session.flush()
    meeting.current_motion_id = motion.id
    db.session.commit()

    auth.login("sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/second",
        data={"seconder_id": str(m1.id)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"same person" in resp.data.lower()
    db.session.refresh(motion)
    assert motion.status == MotionStatus.proposed


def test_member_seconds_normally(client, members, meeting, auth):
    """Regular members can still second motions themselves."""
    _start_meeting(meeting)
    m1 = User.query.filter_by(email="member1@example.com").one()

    motion = Motion(
        meeting_id=meeting.id,
        motion_type=MotionType.main,
        text="Needs a second",
        maker_id=m1.id,
        status=MotionStatus.proposed,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.roll_call,
    )
    db.session.add(motion)
    db.session.flush()
    meeting.current_motion_id = motion.id
    db.session.commit()

    auth.login("member2@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/second",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(motion)
    m2 = User.query.filter_by(email="member2@example.com").one()
    assert motion.seconder_id == m2.id


# ---------------------------------------------------------------------------
# Secretary roll-call voting
# ---------------------------------------------------------------------------


def test_secretary_roll_call_votes(client, secretary, chair, members, meeting, auth):
    """Secretary records individual roll-call votes for all present members."""
    _start_meeting(meeting)
    m1 = User.query.filter_by(email="member1@example.com").one()
    m2 = User.query.filter_by(email="member2@example.com").one()
    m3 = User.query.filter_by(email="member3@example.com").one()
    m4 = User.query.filter_by(email="member4@example.com").one()
    m5 = User.query.filter_by(email="member5@example.com").one()

    motion = _seconded_motion(meeting, m1, m2)

    # Secretary opens vote.
    auth.login("sec@example.com")
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/open-vote",
        follow_redirects=True,
    )
    db.session.refresh(motion)
    assert motion.status == MotionStatus.voting

    # Secretary records all votes at once.
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/secretary-roll-call",
        data={
            f"vote_{m1.id}": "yes",
            f"vote_{m2.id}": "yes",
            f"vote_{m3.id}": "yes",
            f"vote_{m4.id}": "no",
            f"vote_{m5.id}": "abstain",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(motion)
    assert motion.yes_count == 3
    assert motion.no_count == 1
    assert motion.abstain_count == 1

    # Close vote and verify result.
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/close-vote",
        follow_redirects=True,
    )
    db.session.refresh(motion)
    assert motion.result == MotionResult.passed


def test_secretary_roll_call_partial_votes(client, secretary, chair, members, meeting, auth):
    """Secretary can submit partial votes (not all members at once)."""
    _start_meeting(meeting)
    m1 = User.query.filter_by(email="member1@example.com").one()
    m2 = User.query.filter_by(email="member2@example.com").one()

    motion = _seconded_motion(meeting, m1, m2)

    auth.login("sec@example.com")
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/open-vote",
        follow_redirects=True,
    )

    # Only record two votes.
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/secretary-roll-call",
        data={
            f"vote_{m1.id}": "yes",
            f"vote_{m2.id}": "no",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Vote.query.filter_by(motion_id=motion.id).count() == 2


def test_secretary_roll_call_rejects_voice_method(client, secretary, members, meeting, auth):
    """Secretary roll-call route rejects voice-method motions."""
    _start_meeting(meeting)
    m1 = User.query.filter_by(email="member1@example.com").one()
    m2 = User.query.filter_by(email="member2@example.com").one()

    motion = Motion(
        meeting_id=meeting.id,
        motion_type=MotionType.main,
        text="Voice vote",
        maker_id=m1.id,
        seconder_id=m2.id,
        status=MotionStatus.voting,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.voice,
    )
    db.session.add(motion)
    db.session.flush()
    meeting.current_motion_id = motion.id
    db.session.commit()

    auth.login("sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/secretary-roll-call",
        data={f"vote_{m1.id}": "yes"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"roll-call" in resp.data.lower()


def test_member_cannot_use_secretary_roll_call(client, members, meeting, auth):
    """Regular members cannot use the secretary roll-call route."""
    _start_meeting(meeting)
    m1 = User.query.filter_by(email="member1@example.com").one()
    m2 = User.query.filter_by(email="member2@example.com").one()
    motion = _seconded_motion(meeting, m1, m2)

    auth.login("sec@example.com")
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/open-vote",
        follow_redirects=True,
    )

    auth.logout()
    auth.login("member1@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/secretary-roll-call",
        data={f"vote_{m1.id}": "yes"},
        follow_redirects=False,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Secretary can open/close votes and withdraw motions
# ---------------------------------------------------------------------------


def test_secretary_opens_and_closes_vote(client, secretary, members, meeting, auth):
    _start_meeting(meeting)
    m1 = User.query.filter_by(email="member1@example.com").one()
    m2 = User.query.filter_by(email="member2@example.com").one()
    motion = _seconded_motion(meeting, m1, m2)

    auth.login("sec@example.com")
    # Open vote.
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/open-vote",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(motion)
    assert motion.status == MotionStatus.voting

    # Close vote.
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/close-vote",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(motion)
    assert motion.status in {MotionStatus.passed, MotionStatus.failed}


def test_secretary_withdraws_motion(client, secretary, members, meeting, auth):
    _start_meeting(meeting)
    m1 = User.query.filter_by(email="member1@example.com").one()

    motion = Motion(
        meeting_id=meeting.id,
        motion_type=MotionType.main,
        text="To be withdrawn",
        maker_id=m1.id,
        status=MotionStatus.proposed,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.voice,
    )
    db.session.add(motion)
    db.session.flush()
    meeting.current_motion_id = motion.id
    db.session.commit()

    auth.login("sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/withdraw",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(motion)
    assert motion.status == MotionStatus.withdrawn


def test_secretary_enters_manual_tally(client, secretary, members, meeting, auth):
    _start_meeting(meeting)
    m1 = User.query.filter_by(email="member1@example.com").one()
    m2 = User.query.filter_by(email="member2@example.com").one()

    motion = Motion(
        meeting_id=meeting.id,
        motion_type=MotionType.main,
        text="Voice vote",
        maker_id=m1.id,
        seconder_id=m2.id,
        status=MotionStatus.voting,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.voice,
    )
    db.session.add(motion)
    db.session.flush()
    meeting.current_motion_id = motion.id
    db.session.commit()

    auth.login("sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/manual-tally",
        data={
            "yes_count": "5",
            "no_count": "1",
            "abstain_count": "1",
            "submit": "Record tally",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(motion)
    assert motion.yes_count == 5
    assert motion.no_count == 1
    assert motion.abstain_count == 1

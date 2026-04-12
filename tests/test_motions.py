"""Tests for the core motion lifecycle and Robert's Rules logic."""
from datetime import datetime

from app.extensions import db
from app.models import (
    Board,
    BoardMembership,
    BoardRole,
    MajorityRule,
    Meeting,
    MeetingAttendance,
    MeetingStage,
    MeetingStatus,
    MeetingType,
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
        vote_method=VoteMethod.roll_call,
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


def test_deacons_only_vote_blocks_trustee(
    client, make_user, board_of_admin, auth, db
):
    """Trustees cannot vote on a deacons-only motion (Constitution Art VIII §6).

    Only Pastor and Deacons may exercise voting privileges on motions
    pertaining to Board of Deacons responsibilities.
    """
    # Create a pastor, a deacon, and a trustee — all on Board of Admin.
    pastor = make_user(
        email="pastor@example.com", full_name="Pastor", role=Role.pastor
    )
    deacon = make_user(
        email="deacon@example.com", full_name="Deacon", role=Role.deacon
    )
    trustee = make_user(
        email="trustee@example.com", full_name="Trustee", role=Role.trustee
    )

    for user, br in [
        (pastor, BoardRole.pastor),
        (deacon, BoardRole.deacon),
        (trustee, BoardRole.trustee),
    ]:
        db.session.add(
            BoardMembership(
                board_id=board_of_admin.id,
                user_id=user.id,
                role_on_board=br,
                is_voting=True,
            )
        )
    db.session.flush()

    # Create a Board of Admin meeting.
    m = Meeting(
        title="Board Meeting",
        board_id=board_of_admin.id,
        meeting_type=MeetingType.regular,
        scheduled_start=pastor.created_at,
        location="Room",
        status=MeetingStatus.in_progress,
        current_stage=MeetingStage.new_business,
        called_to_order_at=datetime.utcnow(),
        created_by_id=pastor.id,
    )
    db.session.add(m)
    db.session.flush()

    for u in [pastor, deacon, trustee]:
        db.session.add(
            MeetingAttendance(meeting_id=m.id, user_id=u.id, is_present=True)
        )

    # Create a deacons-only motion (roll call so members vote individually).
    motion = Motion(
        meeting_id=m.id,
        motion_type=MotionType.main,
        text="Deacons-only business",
        maker_id=deacon.id,
        seconder_id=pastor.id,
        status=MotionStatus.voting,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.roll_call,
        deacons_only=True,
    )
    db.session.add(motion)
    db.session.flush()
    m.current_motion_id = motion.id
    db.session.commit()

    # Trustee tries to vote → 403
    auth.login("trustee@example.com")
    resp = client.post(
        f"/meetings/{m.id}/live/motions/{motion.id}/vote",
        data={"choice": "yes", "submit": "Cast vote"},
        follow_redirects=False,
    )
    assert resp.status_code == 403

    # Deacon can vote → 200
    auth.logout()
    auth.login("deacon@example.com")
    resp = client.post(
        f"/meetings/{m.id}/live/motions/{motion.id}/vote",
        data={"choice": "yes", "submit": "Cast vote"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Vote.query.filter_by(motion_id=motion.id, user_id=deacon.id).count() == 1


def test_deacons_only_recount_excludes_trustee_votes(app, db, make_user, board_of_admin):
    """Motion.recount() ignores trustee votes on deacons-only motions."""
    pastor = make_user(
        email="pastor@example.com", full_name="Pastor", role=Role.pastor
    )
    deacon = make_user(
        email="deacon@example.com", full_name="Deacon", role=Role.deacon
    )
    trustee = make_user(
        email="trustee@example.com", full_name="Trustee", role=Role.trustee
    )

    for user, br in [
        (pastor, BoardRole.pastor),
        (deacon, BoardRole.deacon),
        (trustee, BoardRole.trustee),
    ]:
        db.session.add(
            BoardMembership(
                board_id=board_of_admin.id,
                user_id=user.id,
                role_on_board=br,
                is_voting=True,
            )
        )
    db.session.flush()

    m = Meeting(
        title="Board Meeting",
        board_id=board_of_admin.id,
        meeting_type=MeetingType.regular,
        scheduled_start=pastor.created_at,
        location="Room",
        status=MeetingStatus.in_progress,
        current_stage=MeetingStage.new_business,
        created_by_id=pastor.id,
    )
    db.session.add(m)
    db.session.flush()

    motion = Motion(
        meeting_id=m.id,
        motion_type=MotionType.main,
        text="Deacons-only motion",
        maker_id=deacon.id,
        status=MotionStatus.voting,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.roll_call,
        deacons_only=True,
    )
    db.session.add(motion)
    db.session.flush()

    # All three vote yes, but trustee's vote should be excluded.
    for u in [pastor, deacon, trustee]:
        db.session.add(
            Vote(motion_id=motion.id, user_id=u.id, choice=VoteChoice.yes)
        )
    db.session.commit()

    motion.recount()
    # Only pastor + deacon counted.
    assert motion.yes_count == 2
    assert motion.no_count == 0
    assert motion.abstain_count == 0


# ---------------------------------------------------------------------------
# Manual tally (voice / show-of-hands) tests
# ---------------------------------------------------------------------------


def test_manual_tally_voice_vote(client, chair, members, meeting, auth):
    """Chair enters manual tally for a voice vote and closes it."""
    _start_meeting(meeting, chair)
    for a in meeting.attendances:
        a.is_present = True
    db.session.commit()

    # Create a voice-method motion that has been seconded.
    m1 = User.query.filter_by(email="member1@example.com").one()
    m2 = User.query.filter_by(email="member2@example.com").one()
    motion = Motion(
        meeting_id=meeting.id,
        motion_type=MotionType.main,
        text="Approve voice vote motion",
        maker_id=m1.id,
        seconder_id=m2.id,
        status=MotionStatus.seconded,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.voice,
    )
    db.session.add(motion)
    db.session.flush()
    meeting.current_motion_id = motion.id
    db.session.commit()

    # Chair opens vote.
    auth.login("chair@example.com")
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/open-vote",
        follow_redirects=True,
    )
    db.session.refresh(motion)
    assert motion.status == MotionStatus.voting

    # Chair enters manual tally.
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/manual-tally",
        data={
            "yes_count": "4",
            "no_count": "1",
            "abstain_count": "1",
            "submit": "Record tally",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(motion)
    assert motion.yes_count == 4
    assert motion.no_count == 1
    assert motion.abstain_count == 1

    # Chair closes vote.
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/close-vote",
        follow_redirects=True,
    )
    db.session.refresh(motion)
    assert motion.result == MotionResult.passed
    assert motion.yes_count == 4  # Not recounted from Vote rows

    # Minutes entry includes voice vote label.
    entry = MinutesEntry.query.filter_by(
        meeting_id=meeting.id,
        entry_type=MinutesEntryType.motion_voted,
    ).first()
    assert entry is not None
    assert "voice vote" in entry.text
    assert "4 yes, 1 no, 1 abstain" in entry.text


def test_cast_vote_rejected_for_voice_method(client, chair, members, meeting, auth):
    """Per-member voting is rejected for voice-method motions."""
    _start_meeting(meeting, chair)
    for a in meeting.attendances:
        a.is_present = True
    db.session.commit()

    m1 = User.query.filter_by(email="member1@example.com").one()
    m2 = User.query.filter_by(email="member2@example.com").one()
    motion = Motion(
        meeting_id=meeting.id,
        motion_type=MotionType.main,
        text="Voice vote motion",
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

    # Member tries to cast a per-member vote → redirected with warning.
    auth.login("member1@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/vote",
        data={"choice": "yes", "submit": "Cast vote"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"voice" in resp.data.lower()
    # No Vote rows should be created.
    assert Vote.query.filter_by(motion_id=motion.id).count() == 0


def test_roll_call_minutes_label(client, chair, members, meeting, auth):
    """Roll-call vote minutes entry includes the [roll call] label."""
    _start_meeting(meeting, chair)
    for a in meeting.attendances:
        a.is_present = True
    db.session.commit()

    m1 = User.query.filter_by(email="member1@example.com").one()
    m2 = User.query.filter_by(email="member2@example.com").one()
    motion = Motion(
        meeting_id=meeting.id,
        motion_type=MotionType.main,
        text="Roll call motion",
        maker_id=m1.id,
        seconder_id=m2.id,
        status=MotionStatus.seconded,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.roll_call,
    )
    db.session.add(motion)
    db.session.flush()
    meeting.current_motion_id = motion.id
    db.session.commit()

    auth.login("chair@example.com")
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/open-vote",
        follow_redirects=True,
    )

    # Cast one vote.
    auth.logout()
    auth.login("member1@example.com")
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/vote",
        data={"choice": "yes", "submit": "Cast vote"},
        follow_redirects=True,
    )

    # Close vote.
    auth.logout()
    auth.login("chair@example.com")
    client.post(
        f"/meetings/{meeting.id}/live/motions/{motion.id}/close-vote",
        follow_redirects=True,
    )

    entry = MinutesEntry.query.filter_by(
        meeting_id=meeting.id,
        entry_type=MinutesEntryType.motion_voted,
    ).first()
    assert entry is not None
    assert "roll call" in entry.text


def test_recount_noop_for_voice_votes(app, db, make_user):
    """Motion.recount() is a no-op for voice votes."""
    u = make_user(email="maker@example.com", full_name="Maker")
    motion = Motion(
        meeting_id=1,
        motion_type=MotionType.main,
        text="Test",
        maker_id=u.id,
        status=MotionStatus.voting,
        requires_majority=MajorityRule.simple,
        vote_method=VoteMethod.voice,
        yes_count=5,
        no_count=2,
        abstain_count=1,
    )
    # recount should not zero-out the manually entered counts.
    motion.recount()
    assert motion.yes_count == 5
    assert motion.no_count == 2
    assert motion.abstain_count == 1

"""Tests for the Phase B board model and board memberships."""
from app.extensions import db
from app.models import (
    Board,
    BoardMembership,
    BoardRole,
    Meeting,
    MeetingAttendance,
    MeetingStatus,
    MeetingType,
    Role,
    User,
    seed_boards,
)


def test_boards_seeded(app):
    """The three canonical boards are seeded on app startup."""
    boards = Board.query.order_by(Board.slug).all()
    slugs = [b.slug for b in boards]
    assert "assembly" in slugs
    assert "board_of_administration" in slugs
    assert "board_of_deacons" in slugs


def test_seed_boards_idempotent(app, db):
    """Calling seed_boards() twice doesn't create duplicates."""
    seed_boards()
    db.session.commit()
    assert Board.query.count() == 3


def test_board_membership_creation(app, db, make_user, board_of_admin):
    """Users can be assigned to boards with a role."""
    pastor = make_user(
        email="pastor@example.com", full_name="Pastor", role=Role.pastor
    )
    bm = BoardMembership(
        board_id=board_of_admin.id,
        user_id=pastor.id,
        role_on_board=BoardRole.pastor,
        is_voting=True,
    )
    db.session.add(bm)
    db.session.commit()

    assert board_of_admin.voting_member_count == 1
    assert pastor.board_memberships[0].board.slug == "board_of_administration"


def test_meeting_has_board(app, db, make_user, board_of_admin):
    """Meeting.board relationship works and shows in board badge."""
    user = make_user(email="u@example.com", full_name="U", role=Role.chair)
    m = Meeting(
        title="Board Meeting",
        board_id=board_of_admin.id,
        meeting_type=MeetingType.regular,
        scheduled_start=user.created_at,
        location="Main hall",
        status=MeetingStatus.scheduled,
        created_by_id=user.id,
    )
    db.session.add(m)
    db.session.commit()

    assert m.board is not None
    assert m.board.slug == "board_of_administration"
    assert m.board.display_name == "Board of Administration"


def test_board_quorum_uses_board_members(app, db, make_user, board_of_admin):
    """Board meeting quorum is based on board membership count, not attendance."""
    # Add 5 voting board members.
    users = []
    for i in range(5):
        u = make_user(
            email=f"bm{i}@example.com", full_name=f"BM {i}", role=Role.deacon
        )
        users.append(u)
        db.session.add(
            BoardMembership(
                board_id=board_of_admin.id,
                user_id=u.id,
                role_on_board=BoardRole.deacon,
                is_voting=True,
            )
        )
    db.session.flush()

    m = Meeting(
        title="Test Board Quorum",
        board_id=board_of_admin.id,
        meeting_type=MeetingType.regular,
        scheduled_start=users[0].created_at,
        location="Room A",
        status=MeetingStatus.scheduled,
        created_by_id=users[0].id,
    )
    db.session.add(m)
    db.session.flush()

    for u in users:
        db.session.add(MeetingAttendance(meeting_id=m.id, user_id=u.id))
    db.session.commit()

    # Board has 5 voting members, quorum = 3.
    assert m.board_voting_member_count == 5
    assert m.quorum_threshold == 3

    # Mark 2 present → not met.
    for a in m.attendances[:2]:
        a.is_present = True
    db.session.commit()
    assert not m.has_quorum

    # Mark a 3rd → met.
    m.attendances[2].is_present = True
    db.session.commit()
    assert m.has_quorum


def test_family_group_stored(app, db, make_user):
    """User.family_group persists correctly."""
    u = make_user(email="fg@example.com", full_name="FG User", role=Role.member)
    u.family_group = "Smith"
    db.session.commit()

    u2 = User.query.filter_by(email="fg@example.com").one()
    assert u2.family_group == "Smith"


def test_new_roles_exist(app):
    """The bylaws-aligned roles are available in the enum."""
    assert Role.pastor.value == "pastor"
    assert Role.deacon.value == "deacon"
    assert Role.trustee.value == "trustee"
    assert Role.assistant_treasurer.value == "assistant_treasurer"


def test_board_attendance_scoping(client, make_user, board_of_deacons, auth):
    """Board meetings scope attendance to board members only."""
    # Create a deacon on the Board of Deacons.
    deacon = make_user(
        email="deacon@example.com", full_name="Deacon", role=Role.deacon
    )
    db.session.add(
        BoardMembership(
            board_id=board_of_deacons.id,
            user_id=deacon.id,
            role_on_board=BoardRole.deacon,
            is_voting=True,
        )
    )
    # Create a non-board member.
    outsider = make_user(
        email="outsider@example.com", full_name="Outsider", role=Role.member
    )
    db.session.commit()

    # Create a Board of Deacons meeting via the route.
    # We need to set up the meeting directly to test attendance scoping.
    m = Meeting(
        title="Deacon Meeting",
        board_id=board_of_deacons.id,
        meeting_type=MeetingType.regular,
        scheduled_start=deacon.created_at,
        location="Room",
        status=MeetingStatus.scheduled,
        created_by_id=deacon.id,
    )
    db.session.add(m)
    db.session.flush()

    # Trigger attendance row generation via the route helper.
    from app.meetings.routes import _ensure_attendance_rows
    _ensure_attendance_rows(m)
    db.session.commit()

    attendance_user_ids = {a.user_id for a in m.attendances}
    # Deacon (board member) should be in attendance.
    assert deacon.id in attendance_user_ids
    # Outsider (not a board member) should NOT be in attendance.
    assert outsider.id not in attendance_user_ids

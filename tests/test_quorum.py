import math
from datetime import datetime

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
)


def test_board_quorum_threshold_and_met(meeting, members, chair):
    """Board meeting (MeetingType.regular): majority of voting members."""
    # 1 chair + 5 members = 6 voting members; quorum = 4.
    assert meeting.voting_member_count == 6
    assert meeting.quorum_threshold == 4
    assert not meeting.has_quorum


def test_board_quorum_flips_as_members_arrive(meeting, chair, members):
    """Board meeting quorum flips when enough voting members are present."""
    # Board meetings require all members notified (Bylaws Art I §§2-3).
    now = datetime.utcnow()
    for a in meeting.attendances:
        a.notified_at = now
    db.session.commit()

    # Mark three present — still below quorum
    present = 0
    for a in meeting.attendances:
        if present < 3 and a.user.is_voting_member:
            a.is_present = True
            present += 1
    db.session.commit()
    assert meeting.present_count == 3
    assert not meeting.has_quorum

    # Mark a fourth present — quorum met
    for a in meeting.attendances:
        if not a.is_present and a.user.is_voting_member:
            a.is_present = True
            break
    db.session.commit()
    assert meeting.present_count == 4
    assert meeting.has_quorum


def test_assembly_quorum_one_third_active(app, db, make_user):
    """Assembly meeting: quorum = ceil(active_members / 3).

    Constitution Art VIII §4: 'No record of any special or regular
    business meeting of the assembly shall be made unless one-third
    or more active members shall be present to constitute a quorum.'
    """
    # Create 9 active members.
    users = []
    for i in range(9):
        users.append(
            make_user(
                email=f"member{i}@example.com",
                full_name=f"Member {i}",
                is_active_member=True,
            )
        )
    db.session.commit()

    # Create an annual_business (assembly) meeting.
    m = Meeting(
        title="Annual Business Meeting",
        meeting_type=MeetingType.annual_business,
        scheduled_start=users[0].created_at,
        location="Sanctuary",
        status=MeetingStatus.scheduled,
        created_by_id=users[0].id,
    )
    db.session.add(m)
    db.session.flush()

    # Attendance rows for all 9 users.
    for u in users:
        db.session.add(MeetingAttendance(meeting_id=m.id, user_id=u.id))
    db.session.commit()

    # Quorum threshold: ceil(9 / 3) = 3
    assert m.quorum_threshold == 3

    # 2 present → not met
    for a in m.attendances[:2]:
        a.is_present = True
    db.session.commit()
    assert m.present_count == 2
    assert not m.has_quorum

    # 3 present → met
    m.attendances[2].is_present = True
    db.session.commit()
    assert m.present_count == 3
    assert m.has_quorum


def test_assembly_quorum_excludes_inactive_members(app, db, make_user):
    """Active-member flag correctly controls quorum denominator."""
    # 6 active + 3 inactive = 9 total
    for i in range(6):
        make_user(
            email=f"active{i}@example.com",
            full_name=f"Active {i}",
            is_active_member=True,
        )
    for i in range(3):
        make_user(
            email=f"inactive{i}@example.com",
            full_name=f"Inactive {i}",
            is_active_member=False,
        )
    db.session.commit()

    m = Meeting(
        title="Special Business Meeting",
        meeting_type=MeetingType.special_business,
        scheduled_start=User.query.first().created_at,
        location="Fellowship Hall",
        status=MeetingStatus.scheduled,
        created_by_id=User.query.first().id,
    )
    db.session.add(m)
    db.session.flush()

    # Only add active members to attendance.
    for u in User.query.filter_by(is_active_member=True).all():
        db.session.add(MeetingAttendance(meeting_id=m.id, user_id=u.id))
    db.session.commit()

    # Quorum based on 6 active members: ceil(6/3) = 2
    assert m.quorum_threshold == 2

    # 1 present → not met
    m.attendances[0].is_present = True
    db.session.commit()
    assert not m.has_quorum

    # 2 present → met
    m.attendances[1].is_present = True
    db.session.commit()
    assert m.has_quorum


def test_board_quorum_requires_all_notified(app, db, make_user, board_of_admin):
    """Board meeting quorum fails if any member is not notified.

    Bylaws Art I §§2-3: quorum requires all members notified.
    """
    users = []
    for i in range(5):
        u = make_user(
            email=f"board{i}@example.com",
            full_name=f"Board Member {i}",
            role=Role.deacon,
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
        title="Board Meeting with Notification",
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

    # Mark 4 present (majority met) but nobody notified → no quorum.
    for a in m.attendances[:4]:
        a.is_present = True
    db.session.commit()
    assert not m.has_quorum
    assert not m.all_members_notified
    assert m.unnotified_count == 5

    # Notify 4 of 5 → still not all notified → no quorum.
    for a in m.attendances[:4]:
        a.notified_at = datetime.utcnow()
    db.session.commit()
    assert not m.all_members_notified
    assert not m.has_quorum

    # Notify the 5th → now all notified, 4 present, quorum met.
    m.attendances[4].notified_at = datetime.utcnow()
    db.session.commit()
    assert m.all_members_notified
    assert m.has_quorum


def test_assembly_quorum_ignores_notification(app, db, make_user):
    """Assembly meetings don't require notification for quorum."""
    users = []
    for i in range(6):
        users.append(
            make_user(
                email=f"asm{i}@example.com",
                full_name=f"Member {i}",
                is_active_member=True,
            )
        )
    db.session.commit()

    m = Meeting(
        title="Assembly Meeting",
        meeting_type=MeetingType.annual_business,
        scheduled_start=users[0].created_at,
        location="Sanctuary",
        status=MeetingStatus.scheduled,
        created_by_id=users[0].id,
    )
    db.session.add(m)
    db.session.flush()

    for u in users:
        db.session.add(MeetingAttendance(meeting_id=m.id, user_id=u.id))
    db.session.commit()

    # Quorum = ceil(6/3) = 2. Nobody notified, but 2 present → quorum met.
    m.attendances[0].is_present = True
    m.attendances[1].is_present = True
    db.session.commit()
    assert not m.all_members_notified  # nobody notified
    assert m.has_quorum  # assembly ignores notification

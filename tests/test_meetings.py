from datetime import datetime, timedelta

from app.models import Board, Meeting


def test_chair_can_create_meeting(client, chair, board_of_admin, auth):
    auth.login("chair@example.com")
    start = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    resp = client.post(
        "/meetings/new",
        data={
            "board_id": board_of_admin.id,
            "title": "April Board",
            "meeting_type": "regular",
            "scheduled_start": start,
            "scheduled_end": "",
            "location": "Fellowship hall",
            "submit": "Save meeting",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Meeting.query.filter_by(title="April Board").count() == 1


def test_pastor_can_create_meeting(client, make_user, board_of_admin, auth):
    make_user(email="pastor@example.com", full_name="Pastor",
              role=__import__("app").models.Role.pastor)
    auth.login("pastor@example.com")
    start = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    resp = client.post(
        "/meetings/new",
        data={
            "board_id": board_of_admin.id,
            "title": "Pastor Board Meeting",
            "meeting_type": "regular",
            "scheduled_start": start,
            "scheduled_end": "",
            "location": "Pastor office",
            "submit": "Save meeting",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Meeting.query.filter_by(title="Pastor Board Meeting").count() == 1


def test_member_cannot_create_meeting(client, make_user, auth):
    make_user(email="m@example.com", full_name="M", role=__import__("app").models.Role.member)
    auth.login("m@example.com")
    resp = client.get("/meetings/new")
    assert resp.status_code == 403


def test_rsvp_persists(client, chair, members, meeting, auth):
    auth.login("member1@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/rsvp",
        data={"rsvp": "yes", "submit": "Update RSVP"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    from app.models import MeetingAttendance, User
    member = User.query.filter_by(email="member1@example.com").one()
    a = MeetingAttendance.query.filter_by(
        meeting_id=meeting.id, user_id=member.id
    ).one()
    assert a.rsvp_status.value == "yes"

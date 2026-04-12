"""Tests for the kiosk check-in feature."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.kiosk import generate_kiosk_token, validate_kiosk_token
from app.models import (
    Meeting,
    MeetingAttendance,
    MeetingStatus,
    MeetingType,
    MinutesEntry,
    Role,
)
from tests.conftest import login


# ---------------------------------------------------------------------------
# Token tests
# ---------------------------------------------------------------------------


def test_generate_and_validate_token(app):
    """A freshly generated token should be valid."""
    token = generate_kiosk_token(42)
    assert validate_kiosk_token(token) == 42


def test_invalid_token_returns_none(app):
    assert validate_kiosk_token("bad-token") is None


# ---------------------------------------------------------------------------
# Kiosk link generation
# ---------------------------------------------------------------------------


def test_kiosk_link_requires_auth(client, meeting):
    """Unauthenticated user is redirected to login."""
    resp = client.post(f"/meetings/{meeting.id}/kiosk-link")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_kiosk_link_requires_secretary_or_chair(client, meeting, members):
    """A plain member cannot generate a kiosk link."""
    login(client, "member1@example.com")
    resp = client.post(f"/meetings/{meeting.id}/kiosk-link")
    assert resp.status_code == 403


def test_kiosk_link_success_for_secretary(client, meeting, secretary):
    """Secretary can generate a kiosk link."""
    login(client, "sec@example.com")
    resp = client.post(f"/meetings/{meeting.id}/kiosk-link")
    assert resp.status_code == 302
    assert "/kiosk/" in resp.headers["Location"]


def test_kiosk_link_success_for_chair(client, meeting, chair):
    """Chair can generate a kiosk link."""
    login(client, "chair@example.com")
    resp = client.post(f"/meetings/{meeting.id}/kiosk-link")
    assert resp.status_code == 302
    assert "/kiosk/" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# Kiosk page
# ---------------------------------------------------------------------------


def test_kiosk_page_loads_with_valid_token(app, client, meeting):
    """Kiosk check-in page loads without login when given a valid token."""
    token = generate_kiosk_token(meeting.id)
    resp = client.get(f"/kiosk/{token}")
    assert resp.status_code == 200
    assert meeting.title.encode() in resp.data
    assert b"Type a name to search" in resp.data


def test_kiosk_page_rejects_invalid_token(client, meeting):
    resp = client.get("/kiosk/invalid-token-here")
    assert resp.status_code == 404


def test_kiosk_page_shows_attendee_names(app, client, meeting, members):
    """Kiosk page shows the names of attendees."""
    token = generate_kiosk_token(meeting.id)
    resp = client.get(f"/kiosk/{token}")
    assert resp.status_code == 200
    for m in members:
        assert m.full_name.encode() in resp.data


# ---------------------------------------------------------------------------
# Kiosk check-in
# ---------------------------------------------------------------------------


def test_kiosk_checkin_marks_present(app, client, meeting, members):
    """Checking in via kiosk sets is_present and arrived_at."""
    token = generate_kiosk_token(meeting.id)
    user = members[0]

    # Ensure not present initially.
    att = MeetingAttendance.query.filter_by(
        meeting_id=meeting.id, user_id=user.id
    ).one()
    assert att.is_present is False
    assert att.arrived_at is None

    resp = client.post(f"/kiosk/{token}/checkin/{user.id}")
    assert resp.status_code == 200

    db.session.refresh(att)
    assert att.is_present is True
    assert att.arrived_at is not None


def test_kiosk_checkin_already_present_is_noop(app, client, meeting, members):
    """Checking in when already present doesn't change arrived_at."""
    token = generate_kiosk_token(meeting.id)
    user = members[0]

    att = MeetingAttendance.query.filter_by(
        meeting_id=meeting.id, user_id=user.id
    ).one()
    att.is_present = True
    att.arrived_at = datetime(2026, 1, 1, 12, 0, 0)
    db.session.commit()

    original_arrived = att.arrived_at
    resp = client.post(f"/kiosk/{token}/checkin/{user.id}")
    assert resp.status_code == 200

    db.session.refresh(att)
    assert att.is_present is True
    assert att.arrived_at == original_arrived


def test_kiosk_checkin_logs_to_minutes(app, client, meeting, members):
    """Kiosk check-in creates a minutes entry with kiosk notation."""
    token = generate_kiosk_token(meeting.id)
    user = members[0]

    client.post(f"/kiosk/{token}/checkin/{user.id}")

    entry = MinutesEntry.query.filter_by(meeting_id=meeting.id).first()
    assert entry is not None
    assert "kiosk check-in" in entry.text
    assert user.full_name in entry.text


def test_kiosk_checkin_invalid_token(client, meeting, members):
    """Check-in with an invalid token returns 404."""
    resp = client.post(f"/kiosk/bad-token/checkin/{members[0].id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Kiosk fragments (HTMX)
# ---------------------------------------------------------------------------


def test_kiosk_quorum_fragment(app, client, meeting):
    """Quorum fragment returns valid HTML."""
    token = generate_kiosk_token(meeting.id)
    resp = client.get(f"/kiosk/{token}/fragment/quorum")
    assert resp.status_code == 200
    assert b"Quorum" in resp.data


def test_kiosk_attendee_fragment_filters_by_query(
    app, client, meeting, members
):
    """Attendee fragment filters by search query."""
    token = generate_kiosk_token(meeting.id)

    # Search for "Member 1" — should find only that member.
    resp = client.get(f"/kiosk/{token}/fragment/attendees?q=Member+1")
    assert resp.status_code == 200
    assert b"Member 1" in resp.data
    # Member 2, 3, 4, 5 should not appear.
    assert b"Member 2" not in resp.data


def test_kiosk_attendee_fragment_filters_by_letter(
    app, client, meeting, chair, secretary
):
    """Attendee fragment filters by starting letter."""
    token = generate_kiosk_token(meeting.id)

    # Filter by 'C' — should find "Chair" but not "Secretary"
    resp = client.get(f"/kiosk/{token}/fragment/attendees?letter=C")
    assert resp.status_code == 200
    assert b"Chair" in resp.data
    assert b"Secretary" not in resp.data

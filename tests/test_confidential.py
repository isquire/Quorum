"""Tests for confidential minutes feature."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app import minutes_logger
from app.extensions import db
from app.models import (
    AgendaCategory,
    AgendaItem,
    Meeting,
    MeetingAttendance,
    MeetingStage,
    MeetingStatus,
    MeetingType,
    MinutesEntry,
    MinutesEntryType,
    Role,
    User,
)
from tests.conftest import login


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


def test_agenda_item_default_not_confidential(app, meeting):
    """AgendaItem.is_confidential defaults to False."""
    item = AgendaItem(
        meeting_id=meeting.id,
        title="Public topic",
        category=AgendaCategory.new_business,
    )
    db.session.add(item)
    db.session.commit()
    assert item.is_confidential is False


def test_agenda_item_confidential_flag(app, meeting):
    """AgendaItem.is_confidential can be set to True."""
    item = AgendaItem(
        meeting_id=meeting.id,
        title="Staff salary review",
        category=AgendaCategory.new_business,
        is_confidential=True,
    )
    db.session.add(item)
    db.session.commit()
    assert item.is_confidential is True


def test_minutes_entry_default_not_confidential(app, meeting):
    """MinutesEntry.is_confidential defaults to False."""
    entry = MinutesEntry(
        meeting_id=meeting.id,
        sequence=1,
        timestamp=datetime(2026, 4, 1, 10, 0),
        entry_type=MinutesEntryType.chair_note,
        text="Public note.",
    )
    db.session.add(entry)
    db.session.commit()
    assert entry.is_confidential is False


# ---------------------------------------------------------------------------
# Minutes logger auto-detection tests
# ---------------------------------------------------------------------------


def test_append_auto_detects_confidential_from_agenda_item(app, meeting):
    """Entries logged while a confidential agenda item is current should
    automatically be marked confidential."""
    item = AgendaItem(
        meeting_id=meeting.id,
        title="Salary discussion",
        category=AgendaCategory.new_business,
        is_confidential=True,
    )
    db.session.add(item)
    db.session.flush()

    meeting.current_agenda_item_id = item.id
    db.session.flush()

    chair = User.query.filter_by(role=Role.chair).first()
    entry = minutes_logger.log_chair_note(meeting, "Discussed salaries.", chair)
    db.session.commit()

    assert entry.is_confidential is True


def test_append_non_confidential_agenda_item(app, meeting):
    """Entries logged under a non-confidential item should not be flagged."""
    item = AgendaItem(
        meeting_id=meeting.id,
        title="Building repairs",
        category=AgendaCategory.new_business,
        is_confidential=False,
    )
    db.session.add(item)
    db.session.flush()

    meeting.current_agenda_item_id = item.id
    db.session.flush()

    chair = User.query.filter_by(role=Role.chair).first()
    entry = minutes_logger.log_chair_note(meeting, "Repair update.", chair)
    db.session.commit()

    assert entry.is_confidential is False


def test_chair_note_explicit_confidential(app, meeting):
    """Chair notes can be explicitly marked confidential regardless of
    current agenda item."""
    chair = User.query.filter_by(role=Role.chair).first()
    entry = minutes_logger.log_chair_note(
        meeting, "Private note.", chair, is_confidential=True
    )
    db.session.commit()

    assert entry.is_confidential is True


# ---------------------------------------------------------------------------
# Minutes detail view redaction tests
# ---------------------------------------------------------------------------


def _create_entries(meeting):
    """Helper: create one public and one confidential entry."""
    public = MinutesEntry(
        meeting_id=meeting.id,
        sequence=1,
        timestamp=datetime(2026, 4, 1, 10, 0),
        entry_type=MinutesEntryType.chair_note,
        text="Public business note.",
        is_confidential=False,
    )
    secret = MinutesEntry(
        meeting_id=meeting.id,
        sequence=2,
        timestamp=datetime(2026, 4, 1, 10, 5),
        entry_type=MinutesEntryType.chair_note,
        text="Staff salary set to $50,000.",
        is_confidential=True,
    )
    db.session.add_all([public, secret])
    db.session.commit()
    return public, secret


def test_officer_sees_full_confidential_content(client, meeting, chair):
    """Officers can see the full text of confidential entries."""
    _create_entries(meeting)
    login(client, "chair@example.com")
    resp = client.get(f"/minutes/{meeting.id}")
    assert b"Staff salary set to $50,000." in resp.data
    assert b"confidential" in resp.data  # badge visible


def test_member_sees_redacted_content(client, meeting, chair, members):
    """Regular members see redacted placeholders for confidential entries."""
    _create_entries(meeting)
    login(client, "member1@example.com")
    resp = client.get(f"/minutes/{meeting.id}")
    assert b"Public business note." in resp.data
    assert b"Staff salary set to $50,000." not in resp.data
    assert b"CONFIDENTIAL" in resp.data


# ---------------------------------------------------------------------------
# Minutes export redaction tests
# ---------------------------------------------------------------------------


def test_officer_export_includes_confidential(client, meeting, chair):
    """Officers get full text in the export."""
    _create_entries(meeting)
    login(client, "chair@example.com")
    resp = client.get(f"/minutes/{meeting.id}/export.txt")
    assert b"Staff salary set to $50,000." in resp.data


def test_member_export_redacts_confidential(client, meeting, chair, members):
    """Members get redacted text in the export."""
    _create_entries(meeting)
    login(client, "member1@example.com")
    resp = client.get(f"/minutes/{meeting.id}/export.txt")
    assert b"Staff salary set to $50,000." not in resp.data
    assert b"CONFIDENTIAL" in resp.data
    assert b"Public business note." in resp.data


# ---------------------------------------------------------------------------
# Agenda item creation with confidential flag
# ---------------------------------------------------------------------------


def test_create_confidential_agenda_item(client, meeting, secretary):
    """Secretary can create a confidential agenda item."""
    login(client, "sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/agenda/items",
        data={
            "title": "Executive compensation",
            "category": "new_business",
            "description": "",
            "presenter_id": 0,
            "is_confidential": "y",
            "submit": "Save",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    item = AgendaItem.query.filter_by(title="Executive compensation").first()
    assert item is not None
    assert item.is_confidential is True


def test_create_non_confidential_agenda_item(client, meeting, secretary):
    """Default agenda items are not confidential."""
    login(client, "sec@example.com")
    resp = client.post(
        f"/meetings/{meeting.id}/agenda/items",
        data={
            "title": "Building maintenance",
            "category": "new_business",
            "description": "",
            "presenter_id": 0,
            "submit": "Save",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    item = AgendaItem.query.filter_by(title="Building maintenance").first()
    assert item is not None
    assert item.is_confidential is False

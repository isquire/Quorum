"""Tests for archive and admin action log features."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.admin_log import log_admin_action
from app.extensions import db
from app.models import (
    AdminAction,
    Meeting,
    MeetingStatus,
    MeetingType,
    Report,
    ReportType,
    Role,
    User,
)
from tests.conftest import login


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin(app):
    user = User(
        email="admin@example.com",
        full_name="Admin User",
        role=Role.admin,
        is_active=True,
        is_voting_member=True,
        is_active_member=True,
    )
    user.set_password("secret123")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture()
def member(app):
    user = User(
        email="member@example.com",
        full_name="Regular Member",
        role=Role.member,
        is_active=True,
        is_voting_member=True,
        is_active_member=True,
    )
    user.set_password("secret123")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture()
def meeting_obj(app, admin):
    m = Meeting(
        title="Board Meeting Q1",
        meeting_type=MeetingType.regular,
        scheduled_start=datetime(2026, 4, 1, 19, 0),
        location="Main hall",
        status=MeetingStatus.adjourned,
        created_by_id=admin.id,
    )
    db.session.add(m)
    db.session.commit()
    return m


@pytest.fixture()
def report_obj(app, admin):
    r = Report(
        title="Treasurer Q1",
        report_type=ReportType.treasurer,
        content="Financials here.",
        submitted_by_id=admin.id,
        submitted_at=datetime(2026, 3, 15, 10, 0),
    )
    db.session.add(r)
    db.session.commit()
    return r


# ---------------------------------------------------------------------------
# AdminAction model / helper tests
# ---------------------------------------------------------------------------


def test_log_admin_action_creates_record(app, admin):
    entry = log_admin_action(
        admin.id, "test_action", "user", 99, "Did a thing."
    )
    db.session.commit()
    assert entry.id is not None
    assert entry.action == "test_action"
    assert entry.target_type == "user"
    assert entry.target_id == 99
    assert entry.detail == "Did a thing."
    assert entry.admin_id == admin.id


# ---------------------------------------------------------------------------
# Meeting archive tests
# ---------------------------------------------------------------------------


def test_meeting_default_not_archived(app, meeting_obj):
    assert meeting_obj.is_archived is False
    assert meeting_obj.archived_at is None


def test_admin_can_archive_meeting(client, admin, meeting_obj):
    login(client, "admin@example.com")
    resp = client.post(
        f"/meetings/{meeting_obj.id}/archive",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(meeting_obj)
    assert meeting_obj.is_archived is True
    assert meeting_obj.archived_at is not None
    assert meeting_obj.archived_by_id == admin.id
    # Verify admin action was logged.
    action = AdminAction.query.filter_by(action="archive_meeting").first()
    assert action is not None
    assert action.target_id == meeting_obj.id


def test_admin_can_unarchive_meeting(client, admin, meeting_obj):
    login(client, "admin@example.com")
    client.post(f"/meetings/{meeting_obj.id}/archive")
    resp = client.post(
        f"/meetings/{meeting_obj.id}/unarchive",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(meeting_obj)
    assert meeting_obj.is_archived is False
    assert meeting_obj.archived_at is None


def test_member_cannot_archive_meeting(client, member, meeting_obj):
    login(client, "member@example.com")
    resp = client.post(f"/meetings/{meeting_obj.id}/archive")
    assert resp.status_code == 403


def test_archived_meeting_hidden_from_list(client, admin, meeting_obj):
    login(client, "admin@example.com")
    client.post(f"/meetings/{meeting_obj.id}/archive")
    resp = client.get("/meetings/")
    assert b"Board Meeting Q1" not in resp.data


def test_archived_meeting_shown_in_archived_view(client, admin, meeting_obj):
    login(client, "admin@example.com")
    client.post(f"/meetings/{meeting_obj.id}/archive")
    resp = client.get("/meetings/?show=archived")
    assert b"Board Meeting Q1" in resp.data


def test_archived_meeting_hidden_from_minutes_list(client, admin, meeting_obj):
    login(client, "admin@example.com")
    client.post(f"/meetings/{meeting_obj.id}/archive")
    resp = client.get("/minutes/")
    assert b"Board Meeting Q1" not in resp.data


# ---------------------------------------------------------------------------
# Report archive tests
# ---------------------------------------------------------------------------


def test_report_default_not_archived(app, report_obj):
    assert report_obj.is_archived is False


def test_admin_can_archive_report(client, admin, report_obj):
    login(client, "admin@example.com")
    resp = client.post(
        f"/reports/{report_obj.id}/archive",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(report_obj)
    assert report_obj.is_archived is True
    action = AdminAction.query.filter_by(action="archive_report").first()
    assert action is not None


def test_admin_can_unarchive_report(client, admin, report_obj):
    login(client, "admin@example.com")
    client.post(f"/reports/{report_obj.id}/archive")
    resp = client.post(
        f"/reports/{report_obj.id}/unarchive",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(report_obj)
    assert report_obj.is_archived is False


def test_member_cannot_archive_report(client, member, report_obj):
    login(client, "member@example.com")
    resp = client.post(f"/reports/{report_obj.id}/archive")
    assert resp.status_code == 403


def test_archived_report_hidden_from_list(client, admin, report_obj):
    login(client, "admin@example.com")
    client.post(f"/reports/{report_obj.id}/archive")
    resp = client.get("/reports/")
    assert b"Treasurer Q1" not in resp.data


def test_archived_report_shown_in_archived_view(client, admin, report_obj):
    login(client, "admin@example.com")
    client.post(f"/reports/{report_obj.id}/archive")
    resp = client.get("/reports/?show=archived")
    assert b"Treasurer Q1" in resp.data


# ---------------------------------------------------------------------------
# Admin action log route tests
# ---------------------------------------------------------------------------


def test_admin_log_page_requires_admin(client, member):
    login(client, "member@example.com")
    resp = client.get("/users/admin-log")
    assert resp.status_code == 403


def test_admin_log_page_shows_actions(client, admin, meeting_obj):
    login(client, "admin@example.com")
    client.post(f"/meetings/{meeting_obj.id}/archive")
    resp = client.get("/users/admin-log")
    assert resp.status_code == 200
    assert b"archive_meeting" in resp.data
    assert b"Admin User" in resp.data


# ---------------------------------------------------------------------------
# Admin actions logged for user operations
# ---------------------------------------------------------------------------


def test_create_user_logs_action(client, admin):
    login(client, "admin@example.com")
    client.post(
        "/users/new",
        data={
            "email": "newuser@example.com",
            "full_name": "New User",
            "role": "member",
            "password": "pass1234",
            "confirm_password": "pass1234",
            "is_voting_member": "y",
            "is_active": "y",
            "is_active_member": "y",
            "family_group": "",
            "committees": "",
            "submit": "Save",
        },
        follow_redirects=True,
    )
    action = AdminAction.query.filter_by(action="create_user").first()
    assert action is not None
    assert "newuser@example.com" in action.detail


def test_remove_user_logs_action(client, admin, member):
    login(client, "admin@example.com")
    client.post(f"/users/{member.id}/deactivate")
    action = AdminAction.query.filter_by(action="remove_user").first()
    assert action is not None
    assert action.target_id == member.id


def test_restore_user_logs_action(client, admin, member):
    login(client, "admin@example.com")
    client.post(f"/users/{member.id}/deactivate")
    client.post(f"/users/{member.id}/activate")
    action = AdminAction.query.filter_by(action="restore_user").first()
    assert action is not None
    assert action.target_id == member.id


def test_removed_user_hidden_from_active_list(client, admin, member):
    login(client, "admin@example.com")
    client.post(f"/users/{member.id}/deactivate")
    resp = client.get("/users/")
    # Email only appears in the table rows, not in flash messages.
    assert b"member@example.com" not in resp.data


def test_removed_user_shown_in_removed_view(client, admin, member):
    login(client, "admin@example.com")
    client.post(f"/users/{member.id}/deactivate")
    resp = client.get("/users/?show=removed")
    assert b"member@example.com" in resp.data

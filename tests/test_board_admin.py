"""Tests for admin board membership and term management."""
from __future__ import annotations

from datetime import date

import pytest

from app.extensions import db
from app.models import (
    AdminAction,
    Board,
    BoardMembership,
    BoardRole,
    Role,
    ServiceTerm,
    TermStatus,
)
from tests.conftest import login


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def member_on_board(db, make_user, board_of_deacons):
    """A user who is a member of the Board of Deacons."""
    user = make_user(
        email="deacon@example.com", full_name="Deacon User", role=Role.deacon
    )
    bm = BoardMembership(
        board_id=board_of_deacons.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        is_voting=True,
    )
    db.session.add(bm)
    db.session.commit()
    return bm


@pytest.fixture()
def active_term(db, member_on_board, board_of_deacons):
    """An active service term for the board member."""
    term = ServiceTerm(
        board_id=board_of_deacons.id,
        user_id=member_on_board.user_id,
        role_on_board=BoardRole.deacon,
        term_start=date(2025, 3, 1),
        term_end=date(2028, 2, 28),
        term_number=1,
        status=TermStatus.active,
    )
    db.session.add(term)
    db.session.commit()
    return term


# ---------------------------------------------------------------------------
# Permission tests
# ---------------------------------------------------------------------------


def test_add_member_requires_admin(client, members, board_of_deacons):
    login(client, "member1@example.com")
    resp = client.get(f"/boards/{board_of_deacons.slug}/members/add")
    assert resp.status_code == 403


def test_edit_member_requires_admin(client, members, member_on_board, board_of_deacons):
    login(client, "member1@example.com")
    resp = client.get(
        f"/boards/{board_of_deacons.slug}/members/{member_on_board.id}/edit"
    )
    assert resp.status_code == 403


def test_remove_member_requires_admin(client, members, member_on_board, board_of_deacons):
    login(client, "member1@example.com")
    resp = client.post(
        f"/boards/{board_of_deacons.slug}/members/{member_on_board.id}/remove"
    )
    assert resp.status_code == 403


def test_edit_term_requires_admin(client, members, active_term):
    login(client, "member1@example.com")
    resp = client.get(f"/boards/terms/{active_term.id}/edit")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Add member
# ---------------------------------------------------------------------------


def test_add_member_page_loads(client, admin, board_of_deacons):
    login(client, "admin@example.com")
    resp = client.get(f"/boards/{board_of_deacons.slug}/members/add")
    assert resp.status_code == 200
    assert b"Add member" in resp.data


def test_add_member_success(client, admin, make_user, board_of_deacons):
    login(client, "admin@example.com")
    new_user = make_user(
        email="newdeacon@example.com", full_name="New Deacon", role=Role.deacon
    )
    db.session.commit()

    resp = client.post(
        f"/boards/{board_of_deacons.slug}/members/add",
        data={
            "user_id": new_user.id,
            "role_on_board": "deacon",
            "is_voting": "y",
            "submit": "Save",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Added New Deacon" in resp.data

    bm = BoardMembership.query.filter_by(
        board_id=board_of_deacons.id, user_id=new_user.id
    ).first()
    assert bm is not None
    assert bm.role_on_board == BoardRole.deacon
    assert bm.is_voting is True


def test_add_member_logs_admin_action(client, admin, make_user, board_of_deacons):
    login(client, "admin@example.com")
    new_user = make_user(
        email="trustee@example.com", full_name="Trustee User", role=Role.trustee
    )
    db.session.commit()

    client.post(
        f"/boards/{board_of_deacons.slug}/members/add",
        data={
            "user_id": new_user.id,
            "role_on_board": "trustee",
            "is_voting": "y",
            "submit": "Save",
        },
    )
    action = AdminAction.query.filter_by(action="add_board_member").first()
    assert action is not None
    assert "Trustee User" in action.detail


def test_add_member_excludes_existing_members(client, admin, member_on_board, board_of_deacons):
    """The add-member form should not list users already on the board."""
    login(client, "admin@example.com")
    resp = client.get(f"/boards/{board_of_deacons.slug}/members/add")
    assert resp.status_code == 200
    # The existing member's name should not appear in the select options.
    assert b"Deacon User" not in resp.data


# ---------------------------------------------------------------------------
# Edit member
# ---------------------------------------------------------------------------


def test_edit_member_page_loads(client, admin, member_on_board, board_of_deacons):
    login(client, "admin@example.com")
    resp = client.get(
        f"/boards/{board_of_deacons.slug}/members/{member_on_board.id}/edit"
    )
    assert resp.status_code == 200
    assert b"Edit membership" in resp.data
    assert b"Deacon User" in resp.data


def test_edit_member_success(client, admin, member_on_board, board_of_deacons):
    login(client, "admin@example.com")
    resp = client.post(
        f"/boards/{board_of_deacons.slug}/members/{member_on_board.id}/edit",
        data={
            "role_on_board": "trustee",
            "is_voting": "",
            "submit": "Save",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    db.session.refresh(member_on_board)
    assert member_on_board.role_on_board == BoardRole.trustee
    assert member_on_board.is_voting is False


def test_edit_member_logs_admin_action(client, admin, member_on_board, board_of_deacons):
    login(client, "admin@example.com")
    client.post(
        f"/boards/{board_of_deacons.slug}/members/{member_on_board.id}/edit",
        data={
            "role_on_board": "secretary",
            "is_voting": "y",
            "submit": "Save",
        },
    )
    action = AdminAction.query.filter_by(action="edit_board_member").first()
    assert action is not None
    assert "Deacon User" in action.detail


def test_edit_member_wrong_board_returns_404(client, admin, member_on_board, board_of_admin):
    """Editing a membership via the wrong board slug gives 404."""
    login(client, "admin@example.com")
    resp = client.get(
        f"/boards/{board_of_admin.slug}/members/{member_on_board.id}/edit"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Remove member
# ---------------------------------------------------------------------------


def test_remove_member_success(client, admin, member_on_board, board_of_deacons):
    login(client, "admin@example.com")
    resp = client.post(
        f"/boards/{board_of_deacons.slug}/members/{member_on_board.id}/remove",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Removed Deacon User" in resp.data

    bm = BoardMembership.query.get(member_on_board.id)
    assert bm is None


def test_remove_member_logs_admin_action(client, admin, member_on_board, board_of_deacons):
    login(client, "admin@example.com")
    client.post(
        f"/boards/{board_of_deacons.slug}/members/{member_on_board.id}/remove",
    )
    action = AdminAction.query.filter_by(action="remove_board_member").first()
    assert action is not None
    assert "Deacon User" in action.detail


def test_remove_member_wrong_board_returns_404(client, admin, member_on_board, board_of_admin):
    login(client, "admin@example.com")
    resp = client.post(
        f"/boards/{board_of_admin.slug}/members/{member_on_board.id}/remove"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Edit term
# ---------------------------------------------------------------------------


def test_edit_term_page_loads(client, admin, active_term):
    login(client, "admin@example.com")
    resp = client.get(f"/boards/terms/{active_term.id}/edit")
    assert resp.status_code == 200
    assert b"Edit service term" in resp.data
    assert b"Deacon User" in resp.data


def test_edit_term_success(client, admin, active_term):
    login(client, "admin@example.com")
    resp = client.post(
        f"/boards/terms/{active_term.id}/edit",
        data={
            "term_start": "2025-04-01",
            "term_end": "2028-03-31",
            "status": "active",
            "notes": "Corrected dates.",
            "submit": "Save changes",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    db.session.refresh(active_term)
    assert active_term.term_start == date(2025, 4, 1)
    assert active_term.term_end == date(2028, 3, 31)
    assert active_term.notes == "Corrected dates."


def test_edit_term_change_status(client, admin, active_term):
    login(client, "admin@example.com")
    client.post(
        f"/boards/terms/{active_term.id}/edit",
        data={
            "term_start": "2025-03-01",
            "term_end": "2028-02-28",
            "status": "completed",
            "notes": "",
            "submit": "Save changes",
        },
    )
    db.session.refresh(active_term)
    assert active_term.status == TermStatus.completed


def test_edit_term_logs_admin_action(client, admin, active_term):
    login(client, "admin@example.com")
    client.post(
        f"/boards/terms/{active_term.id}/edit",
        data={
            "term_start": "2025-03-01",
            "term_end": "2028-02-28",
            "status": "active",
            "notes": "",
            "submit": "Save changes",
        },
    )
    action = AdminAction.query.filter_by(action="edit_service_term").first()
    assert action is not None
    assert "Deacon User" in action.detail


# ---------------------------------------------------------------------------
# Admin logging on existing routes
# ---------------------------------------------------------------------------


def test_record_term_logs_admin_action(client, admin, make_user, board_of_deacons):
    login(client, "admin@example.com")
    user = make_user(
        email="newterm@example.com", full_name="New Term User", role=Role.deacon
    )
    db.session.commit()

    client.post(
        f"/boards/{board_of_deacons.slug}/record-term",
        data={
            "user_id": user.id,
            "role_on_board": "deacon",
            "elected_at_meeting_id": 0,
            "term_start": "2025-03-01",
            "status": "active",
            "notes": "",
            "submit": "Record term",
        },
    )
    action = AdminAction.query.filter_by(action="record_service_term").first()
    assert action is not None
    assert "New Term User" in action.detail


def test_end_term_logs_admin_action(client, admin, active_term):
    login(client, "admin@example.com")
    client.post(
        f"/boards/terms/{active_term.id}/end",
        data={
            "actual_end": "2026-04-12",
            "status": "resigned",
            "notes": "Moved away.",
            "submit": "End term",
        },
    )
    action = AdminAction.query.filter_by(action="end_service_term").first()
    assert action is not None
    assert "Deacon User" in action.detail


# ---------------------------------------------------------------------------
# Board detail shows membership table
# ---------------------------------------------------------------------------


def test_board_detail_shows_members(client, admin, member_on_board, board_of_deacons):
    login(client, "admin@example.com")
    resp = client.get(f"/boards/{board_of_deacons.slug}")
    assert resp.status_code == 200
    assert b"Board members" in resp.data
    assert b"Deacon User" in resp.data
    assert b"Add member" in resp.data


def test_board_detail_shows_edit_link_on_terms(client, admin, active_term, board_of_deacons):
    login(client, "admin@example.com")
    resp = client.get(f"/boards/{board_of_deacons.slug}")
    assert resp.status_code == 200
    assert b"Edit" in resp.data
    assert b"End early" in resp.data

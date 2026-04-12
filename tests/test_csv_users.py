"""Tests for CSV export and import of users."""
from __future__ import annotations

import csv
import io

import pytest

from app.extensions import db
from app.models import AdminAction, Role, User
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


def _make_csv(rows: list[dict]) -> io.BytesIO:
    """Build an in-memory CSV file from a list of dicts."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    buf = io.BytesIO(output.getvalue().encode("utf-8"))
    buf.name = "users.csv"
    return buf


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------


def test_export_csv_requires_admin(client, member):
    login(client, "member@example.com")
    resp = client.get("/users/export-csv")
    assert resp.status_code == 403


def test_export_csv_returns_csv(client, admin, member):
    login(client, "admin@example.com")
    db.session.commit()  # ensure both users are persisted
    resp = client.get("/users/export-csv")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/csv")
    assert b"attachment" in resp.headers["Content-Disposition"].encode()

    # Parse the CSV.
    text = resp.data.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    emails = [r["email"] for r in rows]
    assert "admin@example.com" in emails
    assert "member@example.com" in emails

    # Password column should always be empty.
    for row in rows:
        assert row["password"] == ""


def test_export_csv_logs_admin_action(client, admin):
    login(client, "admin@example.com")
    db.session.commit()
    client.get("/users/export-csv")
    action = AdminAction.query.filter_by(action="export_users_csv").first()
    assert action is not None
    assert action.admin_id == admin.id


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------


def test_import_csv_requires_admin(client, member):
    login(client, "member@example.com")
    resp = client.get("/users/import-csv")
    assert resp.status_code == 403


def test_import_csv_page_loads(client, admin):
    login(client, "admin@example.com")
    resp = client.get("/users/import-csv")
    assert resp.status_code == 200
    assert b"Import users from CSV" in resp.data


def test_import_csv_creates_new_user(client, admin):
    login(client, "admin@example.com")
    db.session.commit()
    csv_file = _make_csv([{
        "email": "newuser@example.com",
        "full_name": "New User",
        "role": "member",
        "password": "password123",
    }])
    resp = client.post(
        "/users/import-csv",
        data={"csv_file": (csv_file, "users.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"1 created" in resp.data

    user = User.query.filter_by(email="newuser@example.com").first()
    assert user is not None
    assert user.full_name == "New User"
    assert user.role == Role.member
    assert user.check_password("password123")


def test_import_csv_updates_existing_user(client, admin, member):
    login(client, "admin@example.com")
    db.session.commit()
    csv_file = _make_csv([{
        "email": "member@example.com",
        "full_name": "Updated Name",
        "role": "deacon",
    }])
    resp = client.post(
        "/users/import-csv",
        data={"csv_file": (csv_file, "users.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"1 updated" in resp.data

    db.session.refresh(member)
    assert member.full_name == "Updated Name"
    assert member.role == Role.deacon


def test_import_csv_skips_invalid_role(client, admin):
    login(client, "admin@example.com")
    db.session.commit()
    csv_file = _make_csv([{
        "email": "bad@example.com",
        "full_name": "Bad Role",
        "role": "superadmin",
        "password": "password123",
    }])
    resp = client.post(
        "/users/import-csv",
        data={"csv_file": (csv_file, "users.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"skipped" in resp.data.lower()
    assert User.query.filter_by(email="bad@example.com").first() is None


def test_import_csv_skips_new_user_without_password(client, admin):
    login(client, "admin@example.com")
    db.session.commit()
    csv_file = _make_csv([{
        "email": "nopw@example.com",
        "full_name": "No Password",
        "role": "member",
    }])
    resp = client.post(
        "/users/import-csv",
        data={"csv_file": (csv_file, "users.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"skipped" in resp.data.lower()
    assert User.query.filter_by(email="nopw@example.com").first() is None


def test_import_csv_missing_required_columns(client, admin):
    login(client, "admin@example.com")
    db.session.commit()
    # CSV missing 'role' column.
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["email", "full_name"])
    writer.writeheader()
    writer.writerow({"email": "x@x.com", "full_name": "X"})
    buf = io.BytesIO(output.getvalue().encode("utf-8"))
    buf.name = "bad.csv"

    resp = client.post(
        "/users/import-csv",
        data={"csv_file": (buf, "bad.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"missing required columns" in resp.data.lower()


def test_import_csv_boolean_fields(client, admin):
    login(client, "admin@example.com")
    db.session.commit()
    csv_file = _make_csv([{
        "email": "booltest@example.com",
        "full_name": "Bool Test",
        "role": "member",
        "is_active": "yes",
        "is_voting_member": "no",
        "is_active_member": "false",
        "password": "password123",
    }])
    resp = client.post(
        "/users/import-csv",
        data={"csv_file": (csv_file, "users.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    user = User.query.filter_by(email="booltest@example.com").first()
    assert user is not None
    assert user.is_active is True
    assert user.is_voting_member is False
    assert user.is_active_member is False


def test_import_csv_updates_password_for_existing_user(client, admin, member):
    login(client, "admin@example.com")
    db.session.commit()
    csv_file = _make_csv([{
        "email": "member@example.com",
        "full_name": "Regular Member",
        "role": "member",
        "password": "newpassword99",
    }])
    client.post(
        "/users/import-csv",
        data={"csv_file": (csv_file, "users.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    db.session.refresh(member)
    assert member.check_password("newpassword99")


def test_import_csv_logs_admin_actions(client, admin):
    login(client, "admin@example.com")
    db.session.commit()
    csv_file = _make_csv([{
        "email": "csvlog@example.com",
        "full_name": "CSV Log",
        "role": "member",
        "password": "password123",
    }])
    client.post(
        "/users/import-csv",
        data={"csv_file": (csv_file, "users.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    action = AdminAction.query.filter_by(action="csv_create_user").first()
    assert action is not None
    assert "csvlog@example.com" in action.detail


def test_import_csv_mixed_create_update_skip(client, admin, member):
    """A single CSV with rows that create, update, and skip."""
    login(client, "admin@example.com")
    db.session.commit()
    csv_file = _make_csv([
        {
            "email": "member@example.com",
            "full_name": "Updated Member",
            "role": "member",
            "password": "",
        },
        {
            "email": "brandnew@example.com",
            "full_name": "Brand New",
            "role": "member",
            "password": "password123",
        },
        {
            "email": "",
            "full_name": "",
            "role": "member",
            "password": "",
        },
    ])
    resp = client.post(
        "/users/import-csv",
        data={"csv_file": (csv_file, "users.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"1 created" in resp.data
    assert b"1 updated" in resp.data
    assert b"1 row" in resp.data.lower()

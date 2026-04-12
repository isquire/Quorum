"""Pytest fixtures."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import (
    Meeting,
    MeetingAttendance,
    MeetingStatus,
    MeetingType,
    Role,
    User,
)


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def client(app):
    return app.test_client()


def _make_user(
    email: str,
    full_name: str,
    role: Role,
    password: str = "secret123",
    is_voting_member: bool = True,
) -> User:
    user = User(
        email=email,
        full_name=full_name,
        role=role,
        is_active=True,
        is_voting_member=is_voting_member,
    )
    user.set_password(password)
    _db.session.add(user)
    _db.session.flush()
    return user


@pytest.fixture()
def make_user(db):
    def _factory(**kwargs):
        defaults = dict(
            email="user@example.com",
            full_name="Test User",
            role=Role.member,
            password="secret123",
            is_voting_member=True,
        )
        defaults.update(kwargs)
        return _make_user(**defaults)

    return _factory


@pytest.fixture()
def admin(make_user):
    return make_user(email="admin@example.com", full_name="Admin", role=Role.admin)


@pytest.fixture()
def chair(make_user):
    return make_user(email="chair@example.com", full_name="Chair", role=Role.chair)


@pytest.fixture()
def secretary(make_user):
    return make_user(email="sec@example.com", full_name="Secretary", role=Role.secretary)


@pytest.fixture()
def members(make_user):
    return [
        make_user(
            email=f"member{i}@example.com",
            full_name=f"Member {i}",
            role=Role.member,
        )
        for i in range(1, 6)
    ]


@pytest.fixture()
def meeting(db, chair, members):
    m = Meeting(
        title="Test meeting",
        meeting_type=MeetingType.regular,
        scheduled_start=datetime.utcnow() + timedelta(hours=1),
        location="Main hall",
        status=MeetingStatus.scheduled,
        created_by_id=chair.id,
    )
    db.session.add(m)
    db.session.flush()
    # Attendance rows for everyone
    users = User.query.all()
    for u in users:
        db.session.add(
            MeetingAttendance(meeting_id=m.id, user_id=u.id)
        )
    db.session.commit()
    return m


def login(client, email: str, password: str = "secret123"):
    return client.post(
        "/auth/login",
        data={"email": email, "password": password, "submit": "Sign in"},
        follow_redirects=True,
    )


@pytest.fixture()
def auth(client):
    class Auth:
        def login(self, email, password="secret123"):
            return login(client, email, password)

        def logout(self):
            return client.get("/auth/logout", follow_redirects=True)

    return Auth()

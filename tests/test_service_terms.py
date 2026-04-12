"""Tests for service term tracking and board officer term limits."""
from datetime import date, datetime, timedelta

import pytest

from app.extensions import db
from app.models import (
    Board,
    BoardMembership,
    BoardRole,
    Meeting,
    MeetingType,
    Role,
    ServiceTerm,
    TERM_RULES,
    TermStatus,
    compute_term_end,
    compute_term_start,
    cooldown_end_date,
    count_consecutive_terms,
    is_eligible_for_term,
)


# ---------------------------------------------------------------------------
# compute_term_start
# ---------------------------------------------------------------------------


def test_compute_term_start_january(app):
    """Jan 15 meeting → Feb 1 term start."""
    dt = datetime(2026, 1, 15, 19, 0)
    assert compute_term_start(dt) == date(2026, 2, 1)


def test_compute_term_start_december(app):
    """Dec meeting → Jan 1 of next year."""
    dt = datetime(2026, 12, 10, 19, 0)
    assert compute_term_start(dt) == date(2027, 1, 1)


def test_compute_term_start_june(app):
    """Jun meeting → Jul 1."""
    dt = datetime(2026, 6, 20, 10, 0)
    assert compute_term_start(dt) == date(2026, 7, 1)


# ---------------------------------------------------------------------------
# compute_term_end
# ---------------------------------------------------------------------------


def test_compute_term_end_two_year(app):
    """Feb 1, 2026 + 2 years → Jan 31, 2028."""
    start = date(2026, 2, 1)
    assert compute_term_end(start, "treasurer") == date(2028, 1, 31)


def test_compute_term_end_three_year(app):
    """Feb 1, 2026 + 3 years → Jan 31, 2029."""
    start = date(2026, 2, 1)
    assert compute_term_end(start, "deacon") == date(2029, 1, 31)


def test_compute_term_end_unknown_role(app):
    """Unknown role raises ValueError."""
    with pytest.raises(ValueError):
        compute_term_end(date(2026, 2, 1), "pastor")


# ---------------------------------------------------------------------------
# ServiceTerm model properties
# ---------------------------------------------------------------------------


def test_service_term_creation(app, db, make_user, board_of_admin):
    user = make_user(email="deacon@test.com", full_name="Deacon Test", role=Role.deacon)
    term = ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        term_start=date(2026, 2, 1),
        term_end=date(2029, 1, 31),
        term_number=1,
        status=TermStatus.active,
    )
    db.session.add(term)
    db.session.commit()

    assert term.id is not None
    assert term.effective_end == date(2029, 1, 31)


def test_effective_end_with_early_exit(app, db, make_user, board_of_admin):
    user = make_user(email="deacon@test.com", full_name="Deacon Test", role=Role.deacon)
    term = ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        term_start=date(2026, 2, 1),
        term_end=date(2029, 1, 31),
        actual_end=date(2027, 6, 15),
        term_number=1,
        status=TermStatus.resigned,
    )
    db.session.add(term)
    db.session.commit()

    assert term.effective_end == date(2027, 6, 15)


def test_is_current_property(app, db, make_user, board_of_admin):
    user = make_user(email="t@test.com", full_name="T", role=Role.treasurer)
    today = date.today()
    term = ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.treasurer,
        term_start=today - timedelta(days=30),
        term_end=today + timedelta(days=365),
        term_number=1,
        status=TermStatus.active,
    )
    db.session.add(term)
    db.session.commit()

    assert term.is_current is True
    assert term.days_remaining is not None
    assert term.days_remaining > 0
    assert term.months_remaining is not None


def test_is_current_false_for_completed(app, db, make_user, board_of_admin):
    user = make_user(email="t@test.com", full_name="T", role=Role.deacon)
    today = date.today()
    term = ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        term_start=today - timedelta(days=30),
        term_end=today + timedelta(days=365),
        term_number=1,
        status=TermStatus.completed,
    )
    db.session.add(term)
    db.session.commit()

    assert term.is_current is False
    assert term.days_remaining is None


# ---------------------------------------------------------------------------
# Consecutive term counting
# ---------------------------------------------------------------------------


def test_count_consecutive_single_term(app, db, make_user, board_of_admin):
    user = make_user(email="d@test.com", full_name="D", role=Role.deacon)
    db.session.add(ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        term_start=date(2023, 2, 1),
        term_end=date(2026, 1, 31),
        term_number=1,
        status=TermStatus.completed,
    ))
    db.session.commit()

    assert count_consecutive_terms(user.id, board_of_admin.id, "deacon") == 1


def test_count_consecutive_with_gap_resets(app, db, make_user, board_of_admin):
    """Two terms with a year gap → count = 1 (most recent only)."""
    user = make_user(email="d@test.com", full_name="D", role=Role.deacon)
    # First term: 2020-02 to 2023-01.
    db.session.add(ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        term_start=date(2020, 2, 1),
        term_end=date(2023, 1, 31),
        term_number=1,
        status=TermStatus.completed,
    ))
    # Second term: 2024-02 to 2027-01 (1-year gap — cooldown).
    db.session.add(ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        term_start=date(2024, 2, 1),
        term_end=date(2027, 1, 31),
        term_number=1,
        status=TermStatus.active,
    ))
    db.session.commit()

    assert count_consecutive_terms(user.id, board_of_admin.id, "deacon") == 1


def test_count_consecutive_treasurer_three(app, db, make_user, board_of_admin):
    """Three back-to-back 2-year treasurer terms → count = 3."""
    user = make_user(email="t@test.com", full_name="T", role=Role.treasurer)
    for i, (start, end) in enumerate([
        (date(2020, 2, 1), date(2022, 1, 31)),
        (date(2022, 2, 1), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2026, 1, 31)),
    ]):
        db.session.add(ServiceTerm(
            board_id=board_of_admin.id,
            user_id=user.id,
            role_on_board=BoardRole.treasurer,
            term_start=start,
            term_end=end,
            term_number=i + 1,
            status=TermStatus.completed,
        ))
    db.session.commit()

    assert count_consecutive_terms(user.id, board_of_admin.id, "treasurer") == 3


# ---------------------------------------------------------------------------
# Cooldown and eligibility
# ---------------------------------------------------------------------------


def test_cooldown_end_date_at_max_deacon(app, db, make_user, board_of_admin):
    """Deacon with 1 completed term (max=1) → cooldown date returned."""
    user = make_user(email="d@test.com", full_name="D", role=Role.deacon)
    db.session.add(ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        term_start=date(2023, 2, 1),
        term_end=date(2026, 1, 31),
        term_number=1,
        status=TermStatus.completed,
    ))
    db.session.commit()

    cd_end = cooldown_end_date(user.id, board_of_admin.id, "deacon")
    assert cd_end is not None
    # Cooldown = 1 year after term end (Jan 31 2026 → Jan 31 2027).
    assert cd_end == date(2027, 1, 31)


def test_cooldown_end_date_below_max_treasurer(app, db, make_user, board_of_admin):
    """Treasurer with 1 of 3 terms served → no cooldown."""
    user = make_user(email="t@test.com", full_name="T", role=Role.treasurer)
    db.session.add(ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.treasurer,
        term_start=date(2024, 2, 1),
        term_end=date(2026, 1, 31),
        term_number=1,
        status=TermStatus.completed,
    ))
    db.session.commit()

    assert cooldown_end_date(user.id, board_of_admin.id, "treasurer") is None


def test_eligible_after_cooldown(app, db, make_user, board_of_admin):
    """Deacon whose cooldown ended in the past → eligible."""
    user = make_user(email="d@test.com", full_name="D", role=Role.deacon)
    db.session.add(ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        term_start=date(2020, 2, 1),
        term_end=date(2023, 1, 31),
        term_number=1,
        status=TermStatus.completed,
    ))
    db.session.commit()

    # Cooldown ended Jan 31, 2024 — well in the past.
    eligible, reason = is_eligible_for_term(user.id, board_of_admin.id, "deacon")
    assert eligible is True
    assert "Eligible" in reason


def test_not_eligible_during_cooldown(app, db, make_user, board_of_admin):
    """Deacon whose term just ended → in cooldown → not eligible."""
    user = make_user(email="d@test.com", full_name="D", role=Role.deacon)
    today = date.today()
    # Term ended recently.
    db.session.add(ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        term_start=today - timedelta(days=365 * 3),
        term_end=today - timedelta(days=30),
        term_number=1,
        status=TermStatus.completed,
    ))
    db.session.commit()

    eligible, reason = is_eligible_for_term(user.id, board_of_admin.id, "deacon")
    assert eligible is False
    assert "cooldown" in reason.lower()


def test_no_cooldown_for_untracked_role(app, db, make_user, board_of_admin):
    """Pastor has no term limits → always eligible."""
    user = make_user(email="p@test.com", full_name="P", role=Role.pastor)
    eligible, reason = is_eligible_for_term(user.id, board_of_admin.id, "pastor")
    assert eligible is True


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


def test_list_boards_page(client, app, db, auth, make_user):
    admin = make_user(email="admin@test.com", full_name="Admin", role=Role.admin)
    auth.login("admin@test.com")
    resp = client.get("/boards/")
    assert resp.status_code == 200
    assert b"Board of Administration" in resp.data


def test_board_detail_shows_terms(client, app, db, auth, make_user, board_of_admin):
    admin = make_user(email="admin@test.com", full_name="Admin", role=Role.admin)
    user = make_user(email="d@test.com", full_name="Deacon D", role=Role.deacon)
    today = date.today()
    db.session.add(ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        term_start=today - timedelta(days=30),
        term_end=today + timedelta(days=365),
        term_number=1,
        status=TermStatus.active,
    ))
    db.session.commit()

    auth.login("admin@test.com")
    resp = client.get("/boards/board_of_administration")
    assert resp.status_code == 200
    assert b"Deacon D" in resp.data
    assert b"Deacon" in resp.data


def test_record_term_admin_only(client, app, db, auth, make_user):
    make_user(email="member@test.com", full_name="Member", role=Role.member)
    auth.login("member@test.com")
    resp = client.get("/boards/board_of_administration/record-term")
    assert resp.status_code == 403


def test_record_term_creates_service_term(client, app, db, auth, make_user, board_of_admin):
    admin = make_user(email="admin@test.com", full_name="Admin", role=Role.admin)
    user = make_user(email="d@test.com", full_name="Deacon D", role=Role.deacon)
    # Create an annual business meeting for the election reference.
    meeting = Meeting(
        title="Annual Business Meeting 2026",
        meeting_type=MeetingType.annual_business,
        scheduled_start=datetime(2026, 1, 15, 19, 0),
        location="Sanctuary",
        created_by_id=admin.id,
    )
    db.session.add(meeting)
    db.session.commit()

    auth.login("admin@test.com")
    resp = client.post(
        f"/boards/board_of_administration/record-term",
        data={
            "user_id": user.id,
            "role_on_board": "deacon",
            "elected_at_meeting_id": meeting.id,
            "term_start": "2026-02-01",
            "notes": "First term",
            "submit": "Record term",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    term = ServiceTerm.query.filter_by(user_id=user.id).first()
    assert term is not None
    assert term.term_start == date(2026, 2, 1)
    assert term.term_end == date(2029, 1, 31)
    assert term.term_number == 1
    assert term.role_on_board == BoardRole.deacon


def test_end_term_sets_actual_end(client, app, db, auth, make_user, board_of_admin):
    admin = make_user(email="admin@test.com", full_name="Admin", role=Role.admin)
    user = make_user(email="d@test.com", full_name="Deacon D", role=Role.deacon)
    today = date.today()
    term = ServiceTerm(
        board_id=board_of_admin.id,
        user_id=user.id,
        role_on_board=BoardRole.deacon,
        term_start=today - timedelta(days=30),
        term_end=today + timedelta(days=365),
        term_number=1,
        status=TermStatus.active,
    )
    db.session.add(term)
    db.session.commit()

    auth.login("admin@test.com")
    resp = client.post(
        f"/boards/terms/{term.id}/end",
        data={
            "actual_end": today.isoformat(),
            "status": "resigned",
            "notes": "Personal reasons",
            "submit": "End term",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    db.session.refresh(term)
    assert term.status == TermStatus.resigned
    assert term.actual_end == today
    assert "Personal reasons" in term.notes

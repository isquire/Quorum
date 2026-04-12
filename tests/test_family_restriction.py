"""Tests for the family-group field and restriction logic.

Constitution Art VII §2.5: no two members of the same immediate family
may serve on the same board.  Phase B stores the family_group field;
full validation is a soft warning in the admin UI.
"""
from app.extensions import db
from app.models import (
    Board,
    BoardMembership,
    BoardRole,
    Role,
    User,
)


def test_family_group_field_persists(app, db, make_user):
    u1 = make_user(email="smith1@example.com", full_name="John Smith", role=Role.deacon)
    u1.family_group = "Smith"
    u2 = make_user(email="smith2@example.com", full_name="Jane Smith", role=Role.deacon)
    u2.family_group = "Smith"
    db.session.commit()

    assert User.query.filter_by(family_group="Smith").count() == 2


def test_same_family_on_same_board_detectable(app, db, make_user, board_of_deacons):
    """Two users with the same family_group on the same board can be detected."""
    u1 = make_user(email="a@example.com", full_name="A Smith", role=Role.deacon)
    u1.family_group = "Smith"
    u2 = make_user(email="b@example.com", full_name="B Smith", role=Role.deacon)
    u2.family_group = "Smith"

    db.session.add(BoardMembership(
        board_id=board_of_deacons.id, user_id=u1.id,
        role_on_board=BoardRole.deacon, is_voting=True,
    ))
    db.session.add(BoardMembership(
        board_id=board_of_deacons.id, user_id=u2.id,
        role_on_board=BoardRole.deacon, is_voting=True,
    ))
    db.session.commit()

    # Query: find family groups with >1 member on the same board.
    from sqlalchemy import func
    conflicts = (
        db.session.query(User.family_group, func.count(User.id))
        .join(BoardMembership, BoardMembership.user_id == User.id)
        .filter(
            BoardMembership.board_id == board_of_deacons.id,
            User.family_group.isnot(None),
            User.family_group != "",
        )
        .group_by(User.family_group)
        .having(func.count(User.id) > 1)
        .all()
    )
    assert len(conflicts) == 1
    assert conflicts[0][0] == "Smith"
    assert conflicts[0][1] == 2


def test_different_families_no_conflict(app, db, make_user, board_of_deacons):
    """Users from different families on the same board produce no conflict."""
    u1 = make_user(email="jones@example.com", full_name="Jones", role=Role.deacon)
    u1.family_group = "Jones"
    u2 = make_user(email="williams@example.com", full_name="Williams", role=Role.deacon)
    u2.family_group = "Williams"

    db.session.add(BoardMembership(
        board_id=board_of_deacons.id, user_id=u1.id,
        role_on_board=BoardRole.deacon, is_voting=True,
    ))
    db.session.add(BoardMembership(
        board_id=board_of_deacons.id, user_id=u2.id,
        role_on_board=BoardRole.deacon, is_voting=True,
    ))
    db.session.commit()

    from sqlalchemy import func
    conflicts = (
        db.session.query(User.family_group, func.count(User.id))
        .join(BoardMembership, BoardMembership.user_id == User.id)
        .filter(
            BoardMembership.board_id == board_of_deacons.id,
            User.family_group.isnot(None),
            User.family_group != "",
        )
        .group_by(User.family_group)
        .having(func.count(User.id) > 1)
        .all()
    )
    assert len(conflicts) == 0

from app.extensions import db


def test_quorum_threshold_and_met(meeting, members, chair):
    # 1 chair + 5 members = 6 voting members; quorum = 4.
    assert meeting.voting_member_count == 6
    assert meeting.quorum_threshold == 4
    assert not meeting.has_quorum


def test_quorum_flips_as_members_arrive(meeting, chair, members):
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

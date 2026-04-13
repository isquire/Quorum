"""Tests for new features: dashboard, print minutes, calendar, backup,
annual report, meeting templates, document repository."""
from __future__ import annotations

import io
from datetime import datetime, date

import pytest

from app.extensions import db
from app.models import (
    Attachment,
    AdminAction,
    Document,
    DocumentCategory,
    DocumentVersion,
    Meeting,
    MeetingAttendance,
    MeetingStatus,
    MeetingTemplate,
    MeetingTemplateItem,
    MeetingType,
    AgendaCategory,
    AgendaItem,
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
def secretary(app):
    user = User(
        email="sec@example.com",
        full_name="Secretary",
        role=Role.secretary,
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


# ---------------------------------------------------------------------------
# Role-based dashboard
# ---------------------------------------------------------------------------


def test_dashboard_loads_for_admin(client, admin):
    login(client, "admin@example.com")
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Total users" in resp.data


def test_dashboard_loads_for_member(client, member):
    login(client, "member@example.com")
    resp = client.get("/")
    assert resp.status_code == 200
    # Members should NOT see admin stats.
    assert b"Total users" not in resp.data


def test_dashboard_shows_unapproved_minutes_for_secretary(client, secretary, meeting_obj):
    login(client, "sec@example.com")
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Minutes awaiting approval" in resp.data


# ---------------------------------------------------------------------------
# Minutes print view
# ---------------------------------------------------------------------------


def test_minutes_print_view_loads(client, admin, meeting_obj):
    login(client, "admin@example.com")
    resp = client.get(f"/minutes/{meeting_obj.id}/print")
    assert resp.status_code == 200
    assert b"Board Meeting Q1" in resp.data
    assert b"Print / Save as PDF" in resp.data


def test_minutes_detail_has_print_link(client, admin, meeting_obj):
    login(client, "admin@example.com")
    resp = client.get(f"/minutes/{meeting_obj.id}")
    assert resp.status_code == 200
    assert b"Print / PDF" in resp.data


# ---------------------------------------------------------------------------
# Term expiration calendar
# ---------------------------------------------------------------------------


def test_term_calendar_loads(client, admin):
    login(client, "admin@example.com")
    resp = client.get("/boards/term-calendar")
    assert resp.status_code == 200
    assert b"Term Expiration Calendar" in resp.data


# ---------------------------------------------------------------------------
# Database backup
# ---------------------------------------------------------------------------


def test_backup_db_requires_admin(client, member):
    login(client, "member@example.com")
    resp = client.get("/users/backup-db")
    assert resp.status_code == 403


def test_restore_db_page_requires_admin(client, member):
    login(client, "member@example.com")
    resp = client.get("/users/restore-db")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Annual report
# ---------------------------------------------------------------------------


def test_annual_report_requires_admin(client, member):
    login(client, "member@example.com")
    resp = client.get("/annual-report")
    assert resp.status_code == 403


def test_annual_report_loads(client, admin):
    login(client, "admin@example.com")
    resp = client.get("/annual-report?year=2026")
    assert resp.status_code == 200
    assert b"Annual Report" in resp.data
    assert b"2026" in resp.data


def test_annual_report_shows_meeting_stats(client, admin, meeting_obj):
    login(client, "admin@example.com")
    resp = client.get("/annual-report?year=2026")
    assert resp.status_code == 200
    assert b"Meetings held" in resp.data


# ---------------------------------------------------------------------------
# Meeting templates
# ---------------------------------------------------------------------------


def test_template_list_loads(client, admin):
    login(client, "admin@example.com")
    resp = client.get("/meetings/templates")
    assert resp.status_code == 200
    assert b"Meeting Templates" in resp.data


def test_create_template(client, secretary):
    login(client, "sec@example.com")
    resp = client.post(
        "/meetings/templates/new",
        data={
            "name": "Standard Board Meeting",
            "description": "Regular monthly agenda",
            "item_title_0": "Approve minutes",
            "item_category_0": "minutes_approval",
            "item_desc_0": "",
            "item_title_1": "Treasurer report",
            "item_category_1": "report",
            "item_desc_1": "Monthly financials",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    template = MeetingTemplate.query.filter_by(name="Standard Board Meeting").first()
    assert template is not None
    assert len(template.items) == 2


def test_save_meeting_as_template(client, secretary, meeting_obj):
    login(client, "sec@example.com")
    # Add some agenda items to the meeting first.
    item = AgendaItem(
        meeting_id=meeting_obj.id,
        order_index=1,
        category=AgendaCategory.new_business,
        title="Budget discussion",
    )
    db.session.add(item)
    db.session.commit()

    resp = client.post(
        f"/meetings/{meeting_obj.id}/save-as-template",
        data={"template_name": "From Q1 meeting"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    template = MeetingTemplate.query.filter_by(name="From Q1 meeting").first()
    assert template is not None
    assert len(template.items) == 1
    assert template.items[0].title == "Budget discussion"


def test_apply_template_to_meeting(client, secretary, meeting_obj):
    login(client, "sec@example.com")
    # Create a template.
    template = MeetingTemplate(
        name="Test Template",
        created_by_id=secretary.id,
    )
    db.session.add(template)
    db.session.flush()
    db.session.add(MeetingTemplateItem(
        template_id=template.id,
        order_index=0,
        category=AgendaCategory.new_business,
        title="Item from template",
    ))
    db.session.commit()

    resp = client.post(
        f"/meetings/{meeting_obj.id}/apply-template",
        data={"template_id": template.id},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    items = AgendaItem.query.filter_by(meeting_id=meeting_obj.id).all()
    assert any(i.title == "Item from template" for i in items)


def test_delete_template(client, admin):
    login(client, "admin@example.com")
    template = MeetingTemplate(
        name="Deletable",
        created_by_id=admin.id,
    )
    db.session.add(template)
    db.session.commit()

    resp = client.post(
        f"/meetings/templates/{template.id}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert MeetingTemplate.query.get(template.id) is None


# ---------------------------------------------------------------------------
# Document repository
# ---------------------------------------------------------------------------


def test_document_list_loads(client, admin):
    login(client, "admin@example.com")
    resp = client.get("/documents/")
    assert resp.status_code == 200
    assert b"Documents" in resp.data


def test_create_document(client, admin):
    login(client, "admin@example.com")
    resp = client.post(
        "/documents/new",
        data={
            "title": "Church Bylaws",
            "category": "bylaws",
            "content": "Article I. Name and purpose.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    doc = Document.query.filter_by(title="Church Bylaws").first()
    assert doc is not None
    assert doc.current_version == 1
    assert len(doc.versions) == 1


def test_edit_document_creates_version(client, admin):
    login(client, "admin@example.com")
    doc = Document(
        title="Test Doc",
        category=DocumentCategory.policy,
        content="v1 content",
        updated_by_id=admin.id,
    )
    db.session.add(doc)
    db.session.flush()
    db.session.add(DocumentVersion(
        document_id=doc.id, version=1, content="v1 content",
        change_summary="Initial", edited_by_id=admin.id,
    ))
    db.session.commit()

    resp = client.post(
        f"/documents/{doc.id}/edit",
        data={
            "title": "Test Doc",
            "category": "policy",
            "content": "v2 updated content",
            "change_summary": "Updated section 1",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(doc)
    assert doc.current_version == 2
    assert doc.content == "v2 updated content"
    assert len(doc.versions) == 2


def test_view_document_version(client, admin):
    login(client, "admin@example.com")
    doc = Document(
        title="Versioned Doc",
        category=DocumentCategory.constitution,
        content="current",
        updated_by_id=admin.id,
    )
    db.session.add(doc)
    db.session.flush()
    db.session.add(DocumentVersion(
        document_id=doc.id, version=1, content="original",
        change_summary="Initial", edited_by_id=admin.id,
    ))
    db.session.commit()

    resp = client.get(f"/documents/{doc.id}/version/1")
    assert resp.status_code == 200
    assert b"original" in resp.data


def test_delete_document(client, admin):
    login(client, "admin@example.com")
    doc = Document(
        title="To Delete",
        category=DocumentCategory.other,
        content="x",
        updated_by_id=admin.id,
    )
    db.session.add(doc)
    db.session.commit()

    resp = client.post(
        f"/documents/{doc.id}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Document.query.get(doc.id) is None


def test_document_requires_admin_to_create(client, member):
    login(client, "member@example.com")
    resp = client.post(
        "/documents/new",
        data={"title": "X", "category": "other", "content": "Y"},
    )
    assert resp.status_code == 403


def test_document_viewable_by_member(client, admin, member):
    login(client, "admin@example.com")
    doc = Document(
        title="Public Doc",
        category=DocumentCategory.bylaws,
        content="Everyone can read",
        updated_by_id=admin.id,
    )
    db.session.add(doc)
    db.session.commit()

    # Switch to member.
    client.get("/auth/logout")
    login(client, "member@example.com")
    resp = client.get(f"/documents/{doc.id}")
    assert resp.status_code == 200
    assert b"Everyone can read" in resp.data


def test_document_filter_by_category(client, admin):
    login(client, "admin@example.com")
    d1 = Document(title="Church Bylaws Doc", category=DocumentCategory.bylaws,
                  content="b", updated_by_id=admin.id)
    d2 = Document(title="Safety Procedures Manual", category=DocumentCategory.policy,
                  content="p", updated_by_id=admin.id)
    db.session.add_all([d1, d2])
    db.session.commit()

    resp = client.get("/documents/?category=bylaws")
    assert resp.status_code == 200
    assert b"Church Bylaws Doc" in resp.data
    assert b"Safety Procedures Manual" not in resp.data


# ---------------------------------------------------------------------------
# Document attachments
# ---------------------------------------------------------------------------


def test_upload_attachment_to_document(client, admin):
    login(client, "admin@example.com")
    doc = Document(
        title="Bylaws with File",
        category=DocumentCategory.bylaws,
        content="text",
        updated_by_id=admin.id,
    )
    db.session.add(doc)
    db.session.commit()

    resp = client.post(
        "/files/upload",
        data={
            "context_type": "document",
            "context_id": str(doc.id),
            "file": (io.BytesIO(b"%PDF-1.4 bylaws pdf"), "bylaws.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    att = Attachment.query.filter_by(document_id=doc.id).first()
    assert att is not None
    assert att.original_filename == "bylaws.pdf"
    assert att.document_id == doc.id


def test_document_view_shows_attachments(client, admin):
    login(client, "admin@example.com")
    doc = Document(
        title="Doc With Attachment",
        category=DocumentCategory.policy,
        content="content",
        updated_by_id=admin.id,
    )
    db.session.add(doc)
    db.session.flush()
    att = Attachment(
        filename="stored_test.pdf",
        original_filename="report.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        uploaded_by_id=admin.id,
        document_id=doc.id,
    )
    db.session.add(att)
    db.session.commit()

    resp = client.get(f"/documents/{doc.id}")
    assert resp.status_code == 200
    assert b"report.pdf" in resp.data
    assert b"Attachments" in resp.data


def test_document_upload_requires_admin(client, member):
    login(client, "member@example.com")
    doc = Document(
        title="Admin Only Upload",
        category=DocumentCategory.other,
        content="x",
        updated_by_id=member.id,
    )
    db.session.add(doc)
    db.session.commit()

    resp = client.post(
        "/files/upload",
        data={
            "context_type": "document",
            "context_id": str(doc.id),
            "file": (io.BytesIO(b"data"), "file.txt"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403


def test_delete_document_removes_attachments(client, admin):
    login(client, "admin@example.com")
    doc = Document(
        title="Doc To Delete",
        category=DocumentCategory.other,
        content="x",
        updated_by_id=admin.id,
    )
    db.session.add(doc)
    db.session.flush()
    att = Attachment(
        filename="will_be_deleted.pdf",
        original_filename="file.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        uploaded_by_id=admin.id,
        document_id=doc.id,
    )
    db.session.add(att)
    db.session.commit()
    att_id = att.id

    resp = client.post(
        f"/documents/{doc.id}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert Attachment.query.get(att_id) is None

import io


def test_upload_rejects_disallowed_extension(client, chair, meeting, auth):
    auth.login("chair@example.com")
    data = {
        "context_type": "meeting",
        "context_id": str(meeting.id),
        "file": (io.BytesIO(b"MZ\x90\x00"), "virus.exe"),
    }
    resp = client.post(
        "/files/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"not allowed" in resp.data


def test_upload_accepts_pdf(client, chair, meeting, auth):
    auth.login("chair@example.com")
    data = {
        "context_type": "meeting",
        "context_id": str(meeting.id),
        "file": (io.BytesIO(b"%PDF-1.4 test pdf content"), "budget.pdf"),
    }
    resp = client.post(
        "/files/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    from app.models import Attachment
    att = Attachment.query.first()
    assert att is not None
    assert att.original_filename == "budget.pdf"
    assert att.meeting_id == meeting.id


def test_download_requires_auth(client, chair, meeting, auth):
    # Upload first
    auth.login("chair@example.com")
    data = {
        "context_type": "meeting",
        "context_id": str(meeting.id),
        "file": (io.BytesIO(b"%PDF-1.4 x"), "doc.pdf"),
    }
    client.post(
        "/files/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    from app.models import Attachment
    att = Attachment.query.first()
    assert att is not None

    auth.logout()
    resp = client.get(f"/files/{att.id}", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.location

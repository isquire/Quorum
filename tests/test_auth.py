def test_login_page_renders(client):
    resp = client.get("/auth/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_login_success_redirects_to_dashboard(client, chair, auth):
    resp = auth.login("chair@example.com")
    assert resp.status_code == 200
    assert b"Dashboard" in resp.data or b"Welcome" in resp.data


def test_login_failure(client, chair):
    resp = client.post(
        "/auth/login",
        data={"email": "chair@example.com", "password": "wrong"},
        follow_redirects=True,
    )
    assert b"Invalid email or password" in resp.data


def test_logout(client, chair, auth):
    auth.login("chair@example.com")
    resp = auth.logout()
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_dashboard_requires_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.location

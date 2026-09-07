"""
tests/test_api.py
-------------------
Integration tests that exercise the running Flask app against a REAL
Supabase project (Flask's test_client + your actual database, no mocking).

WHY integration tests instead of mocks: for a university project this is
much easier to reason about and demo, and it proves the whole stack -
Flask, Supabase, and JWT - actually works together.

SETUP BEFORE RUNNING:
  1. Point your .env at a Supabase project you're OK writing test data
     into (a separate "test" Supabase project is recommended, but not
     required for a class project).
  2. Registration always creates a "tester" role (see routes/auth.py) -
     that's a deliberate security rule, not a bug. So to test admin- and
     developer-only behavior, pre-create one admin and one developer
     account, either:
       a) register them normally, then in Supabase's Table Editor open
          the `users` table and change their `role` column, or
       b) run: python -c "from werkzeug.security import
          generate_password_hash; print(generate_password_hash('Passw0rd!'))"
          and insert rows directly.
     Then put their credentials in a .env.test file (see below) or export
     them as environment variables before running pytest.

RUN WITH:
    pytest tests/test_api.py -v

Covers the 12 required scenarios: register, login, protected-endpoint
rejection, create bug, get bugs, update bug, assign developer, change
status, invalid status transition, add comment, permission checks, and
viewing bug history.
"""

import os
import uuid

import pytest

from app import create_app


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def admin_credentials():
    return {
        "email": os.environ.get("TEST_ADMIN_EMAIL", "admin@example.com"),
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "Passw0rd!"),
    }


@pytest.fixture(scope="module")
def developer_credentials():
    return {
        "email": os.environ.get("TEST_DEVELOPER_EMAIL", "developer@example.com"),
        "password": os.environ.get("TEST_DEVELOPER_PASSWORD", "Passw0rd!"),
    }


def _register_and_login_tester(client):
    """Registers a brand-new tester (unique email each run) and logs in."""
    unique_email = f"tester_{uuid.uuid4().hex[:10]}@example.com"
    password = "Passw0rd!"

    register_resp = client.post(
        "/api/auth/register",
        json={"name": "Test Tester", "email": unique_email, "password": password},
    )
    assert register_resp.status_code == 201
    assert register_resp.get_json()["success"] is True

    login_resp = client.post(
        "/api/auth/login", json={"email": unique_email, "password": password}
    )
    assert login_resp.status_code == 200
    token = login_resp.get_json()["data"]["token"]
    return token, unique_email


def _login(client, email, password):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed for {email}: {resp.get_json()}"
    return resp.get_json()["data"]["token"]


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


# 1 & 2. Register + Login -------------------------------------------------
def test_register_and_login(client):
    token, email = _register_and_login_tester(client)
    assert token


def test_register_duplicate_email_fails(client):
    unique_email = f"dup_{uuid.uuid4().hex[:10]}@example.com"
    client.post(
        "/api/auth/register",
        json={"name": "Dup", "email": unique_email, "password": "Passw0rd!"},
    )
    second = client.post(
        "/api/auth/register",
        json={"name": "Dup", "email": unique_email, "password": "Passw0rd!"},
    )
    assert second.status_code == 400
    assert second.get_json()["success"] is False


# 3. Access protected endpoint without a token -----------------------------
def test_protected_endpoint_requires_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.get_json()["success"] is False


def test_get_current_user(client):
    token, email = _register_and_login_tester(client)
    resp = client.get("/api/auth/me", headers=_auth_header(token))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["user"]["email"] == email


# 4. Create bug -------------------------------------------------------------
def test_create_bug_as_tester(client):
    token, _ = _register_and_login_tester(client)
    resp = client.post(
        "/api/bugs",
        headers=_auth_header(token),
        json={
            "title": "Login button unresponsive",
            "description": "Clicking login does nothing on Safari 17.",
            "severity": "Major",
            "priority": "High",
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["bug"]["status"] == "Open"
    return body["data"]["bug"]["id"]


def test_developer_cannot_create_bug(client, developer_credentials):
    token = _login(client, **developer_credentials)
    resp = client.post(
        "/api/bugs",
        headers=_auth_header(token),
        json={
            "title": "Should not be allowed",
            "description": "Developers cannot create bugs per role rules.",
            "severity": "Minor",
            "priority": "Low",
        },
    )
    assert resp.status_code == 403


# 5. Get bugs -----------------------------------------------------------
def test_get_all_bugs(client):
    token, _ = _register_and_login_tester(client)
    client.post(
        "/api/bugs",
        headers=_auth_header(token),
        json={
            "title": "Sample bug for listing",
            "description": "Used to make sure GET /api/bugs returns data.",
            "severity": "Minor",
            "priority": "Low",
        },
    )
    resp = client.get("/api/bugs", headers=_auth_header(token))
    assert resp.status_code == 200
    assert isinstance(resp.get_json()["data"]["bugs"], list)


# Full workflow: create -> assign -> in progress -> resolved -> closed -----
def test_full_bug_workflow(client, admin_credentials, developer_credentials):
    tester_token, _ = _register_and_login_tester(client)
    admin_token = _login(client, **admin_credentials)
    dev_token = _login(client, **developer_credentials)

    # tester creates the bug
    create_resp = client.post(
        "/api/bugs",
        headers=_auth_header(tester_token),
        json={
            "title": "Checkout page 500 error",
            "description": "Placing an order with a coupon code crashes the server.",
            "severity": "Critical",
            "priority": "Critical",
        },
    )
    bug_id = create_resp.get_json()["data"]["bug"]["id"]

    # get single bug
    get_resp = client.get(f"/api/bugs/{bug_id}", headers=_auth_header(tester_token))
    assert get_resp.status_code == 200

    # 7. admin assigns it to the developer
    dev_me = client.get("/api/auth/me", headers=_auth_header(dev_token)).get_json()
    developer_id = dev_me["data"]["user"]["id"]

    assign_resp = client.put(
        f"/api/bugs/{bug_id}/assign",
        headers=_auth_header(admin_token),
        json={"assigned_to": developer_id},
    )
    assert assign_resp.status_code == 200
    assert assign_resp.get_json()["data"]["bug"]["assigned_to"] == developer_id

    # a tester cannot assign bugs
    forbidden_assign = client.put(
        f"/api/bugs/{bug_id}/assign",
        headers=_auth_header(tester_token),
        json={"assigned_to": developer_id},
    )
    assert forbidden_assign.status_code == 403

    # 8. developer moves Open -> In Progress
    status_resp = client.put(
        f"/api/bugs/{bug_id}/status",
        headers=_auth_header(dev_token),
        json={"status": "In Progress"},
    )
    assert status_resp.status_code == 200
    assert status_resp.get_json()["data"]["bug"]["status"] == "In Progress"

    # 9. INVALID transition: In Progress -> Closed is not allowed
    invalid_resp = client.put(
        f"/api/bugs/{bug_id}/status",
        headers=_auth_header(dev_token),
        json={"status": "Closed"},
    )
    assert invalid_resp.status_code == 400
    assert invalid_resp.get_json()["success"] is False

    # developer resolves it
    resolve_resp = client.put(
        f"/api/bugs/{bug_id}/status",
        headers=_auth_header(dev_token),
        json={"status": "Resolved"},
    )
    assert resolve_resp.status_code == 200

    # 6. update bug (admin changes priority)
    update_resp = client.put(
        f"/api/bugs/{bug_id}",
        headers=_auth_header(admin_token),
        json={"priority": "Medium"},
    )
    assert update_resp.status_code == 200
    assert update_resp.get_json()["data"]["bug"]["priority"] == "Medium"

    # 10. tester adds a comment while verifying the fix
    comment_resp = client.post(
        f"/api/bugs/{bug_id}/comments",
        headers=_auth_header(tester_token),
        json={"comment": "Verified the fix on staging, looks good."},
    )
    assert comment_resp.status_code == 201

    comments_resp = client.get(
        f"/api/bugs/{bug_id}/comments", headers=_auth_header(tester_token)
    )
    assert comments_resp.status_code == 200
    assert len(comments_resp.get_json()["data"]["comments"]) >= 1

    # tester closes the bug
    close_resp = client.put(
        f"/api/bugs/{bug_id}/status",
        headers=_auth_header(tester_token),
        json={"status": "Closed"},
    )
    assert close_resp.status_code == 200
    assert close_resp.get_json()["data"]["bug"]["status"] == "Closed"

    # 12. view bug history - should contain created, assignment_changed,
    # status_changed entries, priority_changed
    history_resp = client.get(
        f"/api/bugs/{bug_id}/history", headers=_auth_header(admin_token)
    )
    assert history_resp.status_code == 200
    actions = [h["action"] for h in history_resp.get_json()["data"]["history"]]
    assert "created" in actions
    assert "assignment_changed" in actions
    assert "status_changed" in actions


# 11. Permission checks ------------------------------------------------------
def test_developer_cannot_delete_bug(client, developer_credentials):
    dev_token = _login(client, **developer_credentials)
    # Use a random UUID - even before the 404 check, permission should 403 first.
    resp = client.delete(f"/api/bugs/{uuid.uuid4()}", headers=_auth_header(dev_token))
    assert resp.status_code == 403

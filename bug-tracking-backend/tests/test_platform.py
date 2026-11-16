"""Projects, owners, admin requests, notifications (incl. live stream), email and support chat."""

import json

from tests.conftest import BUG, PASSWORD


def _register(client, **extra):
    body = {"name": extra.pop("name", "New Person"), "email": extra.pop("email", "new@example.com"), "password": PASSWORD}
    return client.post("/api/auth/register", json={**body, **extra})


def _login(client, email):
    resp = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    return {"Authorization": f"Bearer {data['token']}"}, data


def _notifications(client, headers):
    return client.get("/api/notifications", headers=headers).get_json()["data"]


# --- registration modes -----------------------------------------------------------
def test_register_requires_code_or_admin_request(client, project):
    assert _register(client).status_code == 400  # neither
    bad = _register(client, invite_code="BUG-NOPE99")
    assert bad.status_code == 400 and "Invite code not found" in bad.get_json()["message"]
    assert _register(client, request_admin=True, reason="short").status_code == 400


def test_owner_email_registers_as_owner(client):
    resp = _register(client, email="Owner@Example.com", name="Hein")
    assert resp.status_code == 201 and resp.get_json()["data"]["user"]["role"] == "owner"


def test_admin_request_approval_flow(client, outbox, people, headers):
    _register(client, email="owner@example.com", name="Owner")
    owner_h, _ = _login(client, "owner@example.com")

    resp = _register(client, email="lead@example.com", name="Lead", request_admin=True, reason="I lead the mobile team project")
    assert resp.status_code == 201
    lead_h, session = _login(client, "lead@example.com")
    assert session["project"] is None and session["admin_request"]["status"] == "pending"

    # Owners get a notification and an email.
    assert any("requested admin access" in n["message"] for n in _notifications(client, owner_h)["notifications"])
    assert any(to == "owner@example.com" and "Admin access request" in subject for to, subject, *_ in outbox)

    # No project yet: project-only endpoints are blocked; a second request is a conflict.
    assert client.get("/api/bugs", headers=lead_h).status_code == 403
    assert client.post("/api/admin-requests", json={"reason": "Please approve me again"}, headers=lead_h).status_code == 409

    # Only owners can review.
    assert client.get("/api/admin-requests", headers=headers["admin"]).status_code == 403
    request_id = client.get("/api/admin-requests", headers=owner_h).get_json()["data"]["requests"][0]["id"]
    assert client.put(f"/api/admin-requests/{request_id}", json={"decision": "approve"}, headers=owner_h).status_code == 200
    assert client.put(f"/api/admin-requests/{request_id}", json={"decision": "approve"}, headers=owner_h).status_code == 409
    assert any(to == "lead@example.com" and "approved" in subject for to, subject, *_ in outbox)

    # Approved admin creates a project, gets an invite code and starter FAQs.
    created = client.post("/api/projects", json={"name": "Mobile App"}, headers=lead_h)
    assert created.status_code == 201
    project = created.get_json()["data"]["project"]
    assert project["invite_code"].startswith("BUG-") and project["member_count"] == 1
    assert len(client.get("/api/support/faqs", headers=lead_h).get_json()["data"]["faqs"]) >= 5
    assert client.post("/api/projects", json={"name": "Second"}, headers=lead_h).status_code == 400

    # A newcomer joins with the code as a Tester, and the admin is notified.
    joined = _register(client, email="newbie@example.com", invite_code=project["invite_code"])
    assert joined.get_json()["data"]["user"]["role"] == "tester"
    assert any("joined Mobile App" in n["message"] for n in _notifications(client, lead_h)["notifications"])


def test_rejected_request_can_still_join(client, project):
    _register(client, email="owner@example.com", name="Owner")
    owner_h, _ = _login(client, "owner@example.com")
    _register(client, email="maybe@example.com", request_admin=True, reason="I would like to run a project")
    request_id = client.get("/api/admin-requests", headers=owner_h).get_json()["data"]["requests"][0]["id"]
    client.put(f"/api/admin-requests/{request_id}", json={"decision": "reject"}, headers=owner_h)

    maybe_h, session = _login(client, "maybe@example.com")
    assert session["user"]["role"] == "tester" and session["admin_request"]["status"] == "rejected"
    assert client.post("/api/projects/join", json={"invite_code": "demo23"}, headers=maybe_h).status_code == 200
    assert client.get("/api/bugs", headers=maybe_h).status_code == 200


# --- project isolation -----------------------------------------------------------------
def test_projects_are_isolated(client, db, make_user, login, headers, people, bug_id):
    db.table("projects").insert({"name": "Other", "invite_code": "BUG-OTHER2", "created_by": None}).execute()
    other_project = db.tables["projects"][-1]["id"]
    outsider = login(make_user("admin", "Outsider", "outsider@example.com", project_id=other_project))
    outsider_dev = make_user("developer", "Outside Dev", "outdev@example.com", project_id=other_project)

    assert client.get("/api/bugs", headers=outsider).get_json()["data"]["count"] == 0
    assert client.get(f"/api/bugs/{bug_id}", headers=outsider).status_code == 404
    assert client.get(f"/api/bugs/{bug_id}/comments", headers=outsider).status_code == 404
    assert len(client.get("/api/users", headers=outsider).get_json()["data"]["users"]) == 2
    # Can't assign a bug to someone from another project, or change their role.
    assign = client.put(f"/api/bugs/{bug_id}/assign", json={"assigned_to": outsider_dev["id"]}, headers=headers["admin"])
    assert assign.status_code == 404
    assert client.put(f"/api/users/{people['tester']['id']}/role", json={"role": "developer"}, headers=outsider).status_code == 404


def test_invite_code_regeneration(client, headers):
    old = client.get("/api/projects/current", headers=headers["admin"]).get_json()["data"]["project"]["invite_code"]
    assert "invite_code" not in client.get("/api/projects/current", headers=headers["tester"]).get_json()["data"]["project"]
    assert client.post("/api/projects/current/invite-code", headers=headers["tester"]).status_code == 403
    new = client.post("/api/projects/current/invite-code", headers=headers["admin"]).get_json()["data"]["project"]["invite_code"]
    assert new != old
    assert _register(client, invite_code=old).status_code == 400
    assert _register(client, invite_code=new).status_code == 201


# --- notifications --------------------------------------------------------------------------
def test_workflow_notifications_and_emails(client, outbox, headers, people, bug_id):
    admin_n = _notifications(client, headers["admin"])
    assert any("reported a new high-priority bug" in n["message"] for n in admin_n["notifications"])
    assert _notifications(client, headers["tester"])["unread_count"] == 0  # not notified about own report

    client.put(f"/api/bugs/{bug_id}/assign", json={"assigned_to": people["developer"]["id"]}, headers=headers["admin"])
    dev = _notifications(client, headers["developer"])
    assert dev["unread_count"] == 1 and dev["notifications"][0]["link"] == f"/bugs/{bug_id}"
    assert any(to == "developer@example.com" and subject.startswith("Assigned to you") for to, subject, *_ in outbox)

    for status in ("In Progress", "Resolved"):
        client.put(f"/api/bugs/{bug_id}/status", json={"status": status}, headers=headers["developer"])
    tester = _notifications(client, headers["tester"])
    assert any("Please verify" in n["message"] for n in tester["notifications"])

    client.put(f"/api/bugs/{bug_id}/status", json={"status": "Reopened"}, headers=headers["tester"])
    assert any("reopened" in n["message"] for n in _notifications(client, headers["developer"])["notifications"])

    client.post(f"/api/bugs/{bug_id}/comments", json={"comment": "Still broken on Safari"}, headers=headers["tester"])
    dev = _notifications(client, headers["developer"])
    assert "Still broken on Safari" in dev["notifications"][0]["message"]

    # Read one, then all; you can't touch someone else's.
    first = dev["notifications"][0]["id"]
    assert client.put(f"/api/notifications/{first}/read", headers=headers["tester"]).status_code == 404
    assert client.put(f"/api/notifications/{first}/read", headers=headers["developer"]).get_json()["data"]["unread_count"] == dev["unread_count"] - 1
    client.put("/api/notifications/read-all", headers=headers["developer"])
    assert client.get("/api/notifications/unread-count", headers=headers["developer"]).get_json()["data"]["unread_count"] == 0


def test_email_preference_is_respected(client, outbox, headers, people, bug_id):
    resp = client.put("/api/auth/me/preferences", json={"email_notifications": False}, headers=headers["developer"])
    assert resp.status_code == 200 and resp.get_json()["data"]["user"]["email_notifications"] is False
    client.put(f"/api/bugs/{bug_id}/assign", json={"assigned_to": people["developer"]["id"]}, headers=headers["admin"])
    assert not [m for m in outbox if m[0] == "developer@example.com"]
    assert _notifications(client, headers["developer"])["unread_count"] == 1  # in-app still works
    assert client.put("/api/auth/me/preferences", json={"email_notifications": "no"}, headers=headers["developer"]).status_code == 400


def test_live_stream_pushes_new_notifications(client, headers, people, bug_id):
    resp = client.get(
        "/api/notifications/stream",
        headers=headers["developer"],
        buffered=False,
        environ_overrides={"wsgi.multithread": True},  # like gunicorn's gthread worker
    )
    assert resp.status_code == 200 and resp.mimetype == "text/event-stream"
    chunks = iter(resp.response)
    assert next(chunks).startswith(b"retry:")
    assert b"event: ready" in next(chunks)  # subscribed from here on

    client.put(f"/api/bugs/{bug_id}/assign", json={"assigned_to": people["developer"]["id"]}, headers=headers["admin"])
    for chunk in chunks:
        if chunk.startswith(b"event: notification"):
            payload = json.loads(chunk.decode().split("data: ", 1)[1])
            assert "assigned you" in payload["notification"]["message"]
            break
    else:
        raise AssertionError("no live notification received")
    resp.close()
    assert client.get("/api/notifications/stream").status_code == 401


# --- support chat -----------------------------------------------------------------------------
def test_support_faqs_and_questions(client, headers, people):
    admin, tester = headers["admin"], headers["tester"]
    faq = client.post("/api/support/faqs", json={"question": "Where are the logs?", "answer": "In the Logs tab.", "keywords": "logs"}, headers=admin)
    assert faq.status_code == 201
    faq_id = faq.get_json()["data"]["faq"]["id"]
    assert client.post("/api/support/faqs", json={"question": "Hack?", "answer": "No"}, headers=tester).status_code == 403

    client.post(f"/api/support/faqs/{faq_id}/hit", headers=tester)
    faqs = client.get("/api/support/faqs", headers=tester).get_json()["data"]["faqs"]
    assert faqs[0]["id"] == faq_id and faqs[0]["hits"] == 1  # most asked first

    asked = client.post("/api/support/questions", json={"question": "How do I export bugs to Excel?"}, headers=tester)
    assert asked.status_code == 201
    assert any("asked:" in n["message"] for n in _notifications(client, admin)["notifications"])
    question_id = asked.get_json()["data"]["question"]["id"]

    assert len(client.get("/api/support/questions", headers=tester).get_json()["data"]["questions"]) == 1  # own only
    answered = client.put(
        f"/api/support/questions/{question_id}/answer",
        json={"answer": "Exporting isn't available yet.", "add_to_faq": True},
        headers=admin,
    )
    assert answered.status_code == 200 and answered.get_json()["data"]["faq"]["question"].startswith("How do I export")
    assert any("answered your question" in n["message"] for n in _notifications(client, tester)["notifications"])

    assert client.delete(f"/api/support/faqs/{faq_id}", headers=admin).status_code == 200
    assert client.delete(f"/api/support/faqs/{faq_id}", headers=admin).status_code == 404


def test_owner_sees_all_projects(client, headers, bug_id):
    _register(client, email="owner@example.com", name="Owner")
    owner_h, session = _login(client, "owner@example.com")
    assert session["project"] is None
    projects = client.get("/api/projects", headers=owner_h).get_json()["data"]["projects"]
    assert projects[0]["bug_count"] == 1 and projects[0]["member_count"] == 4
    assert client.get("/api/projects", headers=headers["admin"]).status_code == 403
    assert client.get("/api/bugs", headers=owner_h).status_code == 403


def test_starter_faqs_can_be_added_to_an_empty_project(client, headers):
    # The `project` fixture has no FAQs, like a project created by the migration.
    assert client.get("/api/support/faqs", headers=headers["tester"]).get_json()["data"]["faqs"] == []
    assert client.post("/api/support/faqs/defaults", headers=headers["tester"]).status_code == 403

    first = client.post("/api/support/faqs/defaults", headers=headers["admin"])
    assert first.status_code == 201 and len(first.get_json()["data"]["faqs"]) >= 5
    count = len(client.get("/api/support/faqs", headers=headers["tester"]).get_json()["data"]["faqs"])

    again = client.post("/api/support/faqs/defaults", headers=headers["admin"])  # safe to repeat
    assert again.status_code == 200 and again.get_json()["data"]["faqs"] == []
    assert len(client.get("/api/support/faqs", headers=headers["tester"]).get_json()["data"]["faqs"]) == count


def test_stream_refuses_single_threaded_servers(client, headers):
    # gunicorn's default "sync" worker handles one request at a time: an open
    # stream used to block every other request (the FAQ failed with 5xx).
    resp = client.get("/api/notifications/stream", headers=headers["developer"])  # test client = single-threaded
    assert resp.status_code == 503 and "every few seconds" in resp.get_json()["message"]
    multi = client.get(
        "/api/notifications/stream",
        headers=headers["developer"],
        environ_overrides={"wsgi.multithread": True, "wsgi.multiprocess": True},  # several worker processes
    )
    assert multi.status_code == 503
    # Everything else keeps working regardless.
    assert client.get("/api/support/faqs", headers=headers["developer"]).status_code == 200


def test_setup_check_reports_problems(client, headers):
    report = client.get("/api/health/setup").get_json()
    assert report["data"]["database_tables"]["faqs"] == "ok"
    assert report["data"]["faq_count"] == 0 and report["success"] is False
    assert any("No FAQs" in p for p in report["data"]["problems"])
    assert any("Start Command" in fix for fix in report["data"]["how_to_fix"])  # single-threaded test server

    client.post("/api/support/faqs/defaults", headers=headers["admin"])
    good = client.get("/api/health/setup", environ_overrides={"wsgi.multithread": True}).get_json()
    assert good["success"] is True and good["data"]["live_notifications"] == "on"


def test_missing_table_gives_actionable_error(client, db, headers):
    del db.tables["faqs"]  # like a database where the migration wasn't run
    resp = client.get("/api/support/faqs", headers=headers["tester"])
    assert resp.status_code == 500 and "Run the latest SQL migration" in resp.get_json()["message"]
    assert client.get("/api/health/setup").get_json()["data"]["database_tables"]["faqs"] == "missing or out of date"


def test_permission_denied_gives_actionable_error(client, db, headers):
    # The real error from Supabase when a table was never granted to service_role.
    db.denied = {"faqs", "support_questions"}
    resp = client.get("/api/support/faqs", headers=headers["tester"])
    assert resp.status_code == 500 and "003_grant_service_role.sql" in resp.get_json()["message"]
    report = client.get("/api/health/setup").get_json()["data"]
    assert report["database_tables"]["faqs"] == "no permission"
    assert report["database_tables"]["bugs"] == "ok"
    assert any("003_grant_service_role.sql" in fix for fix in report["how_to_fix"])


def test_database_network_errors_are_temporary_503(client, db, headers, monkeypatch):
    import httpx

    def boom(self):
        raise httpx.ReadError("[WinError 10035] A non-blocking socket operation could not be completed immediately")

    monkeypatch.setattr(type(db.table("faqs")), "execute", boom)
    resp = client.get("/api/health/setup")  # unauthenticated path still answers
    assert resp.status_code == 200
    resp = client.get("/api/support/faqs", headers=headers["tester"])
    assert resp.status_code == 503 and "try again" in resp.get_json()["message"].lower()


def test_real_supabase_client_uses_http1():
    """WinError 10035 came from one shared HTTP/2 connection used by many threads."""
    pytest = __import__("pytest")
    supabase = pytest.importorskip("supabase")
    from app.services.supabase_http import use_http1_for_postgrest

    use_http1_for_postgrest()
    key = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.c2lnbmF0dXJl"
    session = supabase.create_client("https://example.supabase.co", key).postgrest.session
    assert session._transport._pool._http2 is False
    assert session.headers.get("apikey") == key and str(session.base_url).endswith("/rest/v1/")

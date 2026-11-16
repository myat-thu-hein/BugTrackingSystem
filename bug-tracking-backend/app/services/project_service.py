"""
app/services/project_service.py
---------------------------------
Projects, invite codes and the starter FAQ every new project gets.
"""

import secrets

from flask import current_app

from app.extensions import get_db

# No 0/O or 1/I/L, so codes are easy to read aloud and type.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_invite_code():
    """Random, unguessable, human-friendly code such as BUG-7KQ2X9."""
    db = get_db()
    for _ in range(10):
        code = "BUG-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
        if not db.table("projects").select("id").eq("invite_code", code).limit(1).execute().data:
            return code
    raise RuntimeError("Could not generate a unique invite code")


def normalize_invite_code(value):
    """Accepts 'bug-7kq2x9', ' BUG-7KQ2X9 ' or '7KQ2X9'."""
    if not isinstance(value, str):
        return ""
    code = value.strip().upper().replace(" ", "")
    if code and not code.startswith("BUG-"):
        code = f"BUG-{code}"
    return code


def find_project_by_code(code):
    rows = get_db().table("projects").select("*").eq("invite_code", normalize_invite_code(code)).limit(1).execute().data
    return rows[0] if rows else None


def get_project(project_id):
    if not project_id:
        return None
    rows = get_db().table("projects").select("*").eq("id", project_id).limit(1).execute().data
    return rows[0] if rows else None


def is_owner_email(email):
    owners = current_app.config.get("OWNER_EMAILS", "") or ""
    return email.lower() in {e.strip().lower() for e in owners.split(",") if e.strip()}


def serialize_project(project, *, include_code):
    if not project:
        return None
    data = {"id": project["id"], "name": project["name"], "created_at": project.get("created_at")}
    if include_code:
        data["invite_code"] = project["invite_code"]
    return data


# --- starter FAQ ------------------------------------------------------------
DEFAULT_FAQS = [
    (
        "How do I report a bug?",
        "Testers can click 'Create Bug' in the sidebar. Give it a clear title, the steps to reproduce, what you "
        "expected and what actually happened, then pick a priority and severity.",
        "report create new submit add file log",
    ),
    (
        "Why can't I see some bugs?",
        "Developers only see bugs that are assigned to them. Testers and admins see every bug in the project.",
        "see missing hidden visible list developer",
    ),
    (
        "How do I change a bug's status?",
        "Open the bug and use the buttons in the Status panel. Each role can only make its own moves: developers "
        "start and resolve work, testers close or reopen resolved bugs.",
        "status change move workflow progress resolve",
    ),
    (
        "How do I reopen a bug that isn't really fixed?",
        "When a bug is Resolved, a tester can click 'Reopen'. It goes back to the developer as Reopened. Add a "
        "comment explaining what still fails.",
        "reopen fixed again broken still fail verify",
    ),
    (
        "Can I reopen a closed bug?",
        "No. Closed is the final state, meaning a tester verified the fix. If the problem comes back, report a new "
        "bug and mention the old bug's ID (for example #1a2b3c4d) in the description.",
        "closed reopen final undo",
    ),
    (
        "How do I become a developer or admin?",
        "Everyone joins a project as a Tester. Your project admin can change your role on the Users page. To run "
        "your own project, register with 'Request admin access' and the owners will review it.",
        "role developer admin promote permission become change",
    ),
    (
        "How do I invite my team?",
        "Admins can find the project's invite code on the Dashboard. Teammates enter it when they register. You can "
        "regenerate the code at any time if it was shared by mistake.",
        "invite code join team member add project",
    ),
    (
        "How do I turn off email notifications?",
        "Go to Settings and switch off 'Email notifications'. You will still see notifications in the app.",
        "email notifications turn off stop unsubscribe settings",
    ),
    (
        "Who do I contact if I'm stuck?",
        "Type your question in this chat. If there is no answer here, send it to your project admin and you'll "
        "get a notification when they reply.",
        "contact help support admin stuck question",
    ),
]


def seed_default_faqs(project_id):
    """
    Add the starter FAQs this project doesn't have yet (matched by question
    text), so it is safe to run more than once. Returns the rows added.
    """
    db = get_db()
    existing = {
        row["question"].strip().lower()
        for row in db.table("faqs").select("question").eq("project_id", project_id).execute().data
    }
    added = []
    for question, answer, keywords in DEFAULT_FAQS:
        if question.lower() in existing:
            continue
        added.append(
            db.table("faqs")
            .insert({"project_id": project_id, "question": question, "answer": answer, "keywords": keywords, "hits": 0})
            .execute()
            .data[0]
        )
    return added

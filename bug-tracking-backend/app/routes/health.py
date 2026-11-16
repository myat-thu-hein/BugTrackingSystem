"""
app/routes/health.py
----------------------
  GET /api/health        - is the API up?
  GET /api/health/setup  - is the deployment set up correctly? (open it in a browser)

/setup checks, in plain language, the things that made features fail on a
real deployment: every table and the columns the app needs exist in
Supabase, and whether this server can run live notifications. It reveals
only table names and yes/no answers, never data.
"""

from flask import Blueprint, request

from app.errors import is_permission_error
from app.extensions import get_db
from app.routes.notifications import live_stream_supported

health_bp = Blueprint("health", __name__)

# table -> columns the code relies on (added by the migrations)
REQUIRED_SCHEMA = {
    "users": "id, role, project_id, email_notifications",
    "projects": "id, invite_code",
    "bugs": "id, project_id",
    "comments": "id",
    "bug_history": "id",
    "notifications": "id, is_read",
    "admin_requests": "id, status",
    "faqs": "id, hits",
    "support_questions": "id, status",
}

FIX_SCHEMA = (
    "Run bug-tracking-backend/sql/migrations/001_projects_notifications_support.sql "
    "(and 002_seed_starter_faqs.sql) in the Supabase SQL Editor."
)
FIX_PERMISSIONS = (
    "Run bug-tracking-backend/sql/migrations/003_grant_service_role.sql in the Supabase SQL Editor "
    "(lets the backend's service_role use every table)."
)
FIX_WORKER = (
    "In Render -> your backend service -> Settings -> Start Command, use: "
    "gunicorn run:app --bind 0.0.0.0:$PORT --worker-class gthread --workers 1 --threads 32 --timeout 120"
)


@health_bp.route("", methods=["GET"])
def health():
    return {"success": True, "message": "Bug Tracking API is running"}


@health_bp.route("/setup", methods=["GET"])
def setup_check():
    db = get_db()
    tables, problems = {}, []
    for table, columns in REQUIRED_SCHEMA.items():
        try:
            db.table(table).select(columns).limit(1).execute()
            tables[table] = "ok"
        except Exception as exc:  # noqa: BLE001 - we're reporting, not handling
            if is_permission_error(exc):
                tables[table] = "no permission"
                problems.append(f"The backend isn't allowed to use table '{table}' (permission denied).")
            else:
                tables[table] = "missing or out of date"
                problems.append(f"Table '{table}' is missing or lacks columns ({columns}): {str(exc)[:160]}")

    faq_count = None
    if tables.get("faqs") == "ok":
        faq_count = len(db.table("faqs").select("id").execute().data)
        if faq_count == 0:
            problems.append("No FAQs exist yet, so the help chat can't answer. Run 002_seed_starter_faqs.sql "
                            "or click 'Add starter FAQs' in the Help Center.")

    live = live_stream_supported(request.environ)
    if not live:
        problems.append("Live notifications are off on this server (it handles one request at a time). "
                        "The app still works and checks every few seconds. " + FIX_WORKER)

    fixes = []
    if "no permission" in tables.values():
        fixes.append(FIX_PERMISSIONS)
    if "missing or out of date" in tables.values():
        fixes.append(FIX_SCHEMA)
    if not live:
        fixes.append(FIX_WORKER)

    return {
        "success": not problems,
        "message": "Everything is set up correctly" if not problems else f"{len(problems)} problem(s) found",
        "data": {
            "database_tables": tables,
            "faq_count": faq_count,
            "live_notifications": "on" if live else "off (polling every few seconds)",
            "problems": problems,
            "how_to_fix": fixes,
        },
    }

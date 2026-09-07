"""
app/routes/bugs.py
--------------------
Core bug-tracking endpoints:

  POST   /api/bugs              - create a bug            (tester)
  GET    /api/bugs               - list bugs                (all roles, filtered)
  GET    /api/bugs/<id>          - get one bug               (all roles, if permitted)
  PUT    /api/bugs/<id>          - update title/description/severity/priority
  DELETE /api/bugs/<id>          - delete a bug              (admin)
  PUT    /api/bugs/<id>/assign   - assign a bug to a developer (admin)
  PUT    /api/bugs/<id>/status   - change status, with workflow validation
  GET    /api/bugs/<id>/history  - view a bug's audit trail

Role rules (see also middleware/permissions.py):
  - Tester    : create bugs, view bugs, verify/close/reopen resolved bugs
  - Developer : view + update bugs assigned to them, move them through the
                "working" part of the workflow (Open -> In Progress -> Resolved)
  - Admin     : full access - assign bugs, edit/delete any bug, view everything

Every change to status/priority/severity/assignment writes a row into
bug_history so the team has a full audit trail (see sql/schema.sql).
"""

from datetime import datetime, timezone

from flask import Blueprint, request, g, current_app

from app.middleware.auth import token_required
from app.middleware.permissions import role_required
from app.utils.responses import success_response, error_response
from app.utils.validators import (
    require_fields,
    is_valid_severity,
    is_valid_priority,
    is_valid_status,
    is_valid_status_transition,
)

bugs_bp = Blueprint("bugs", __name__)

# Which (old_status -> new_status) moves each role is allowed to make.
# This is layered ON TOP OF the general STATUS_TRANSITIONS workflow check -
# a move must pass BOTH checks to be allowed.
ROLE_STATUS_MOVES = {
    "developer": {("Open", "In Progress"), ("In Progress", "Resolved"), ("Reopened", "In Progress")},
    "tester": {("Resolved", "Closed"), ("Resolved", "Reopened")},
    "admin": None,  # None means "any transition that passes the workflow check"
}


def _record_history(supabase, bug_id, user_id, action, old_value, new_value):
    supabase.table("bug_history").insert(
        {
            "bug_id": bug_id,
            "user_id": user_id,
            "action": action,
            "old_value": str(old_value) if old_value is not None else None,
            "new_value": str(new_value) if new_value is not None else None,
        }
    ).execute()


def _get_bug_or_none(supabase, bug_id):
    result = supabase.table("bugs").select("*").eq("id", bug_id).limit(1).execute()
    return result.data[0] if result.data else None


def _can_view_bug(user, bug):
    if user["role"] in ("admin", "tester"):
        return True
    # developer: only bugs assigned to them
    return bug.get("assigned_to") == user["id"]


@bugs_bp.route("", methods=["POST"])
@token_required
@role_required("tester")
def create_bug():
    supabase = current_app.config["SUPABASE_CLIENT"]
    data = request.get_json(silent=True) or {}

    missing = require_fields(data, ["title", "description", "severity", "priority"])
    if missing:
        return error_response(f"Missing required field(s): {', '.join(missing)}", 400)

    title = data["title"].strip()
    description = data["description"].strip()
    severity = data["severity"]
    priority = data["priority"]

    if len(title) < 3:
        return error_response("Bug title must be at least 3 characters", 400)
    if len(description) < 10:
        return error_response("Bug description must be at least 10 characters", 400)
    if not is_valid_severity(severity):
        return error_response("Invalid severity value", 400)
    if not is_valid_priority(priority):
        return error_response("Invalid priority value", 400)

    insert_result = (
        supabase.table("bugs")
        .insert(
            {
                "title": title,
                "description": description,
                "severity": severity,
                "priority": priority,
                "status": "Open",
                "reported_by": g.current_user["id"],
                "assigned_to": None,
            }
        )
        .execute()
    )
    bug = insert_result.data[0]
    _record_history(supabase, bug["id"], g.current_user["id"], "created", None, "Open")

    return success_response("Bug created successfully", {"bug": bug}, 201)


@bugs_bp.route("", methods=["GET"])
@token_required
def list_bugs():
    supabase = current_app.config["SUPABASE_CLIENT"]
    query = supabase.table("bugs").select("*")

    # Developers only ever see bugs assigned to them.
    if g.current_user["role"] == "developer":
        query = query.eq("assigned_to", g.current_user["id"])

    # Optional filters, e.g. GET /api/bugs?status=Open&priority=High
    for param, column in (("status", "status"), ("severity", "severity"), ("priority", "priority")):
        value = request.args.get(param)
        if value:
            query = query.eq(column, value)

    # Admin/tester can also filter by assigned_to explicitly if they want.
    assigned_to = request.args.get("assigned_to")
    if assigned_to and g.current_user["role"] != "developer":
        query = query.eq("assigned_to", assigned_to)

    result = query.order("created_at", desc=True).execute()
    return success_response("Bugs retrieved", {"bugs": result.data, "count": len(result.data)})


@bugs_bp.route("/<bug_id>", methods=["GET"])
@token_required
def get_bug(bug_id):
    supabase = current_app.config["SUPABASE_CLIENT"]
    bug = _get_bug_or_none(supabase, bug_id)
    if not bug:
        return error_response("Bug not found", 404)
    if not _can_view_bug(g.current_user, bug):
        return error_response("You do not have permission to view this bug", 403)
    return success_response("Bug retrieved", {"bug": bug})


@bugs_bp.route("/<bug_id>", methods=["PUT"])
@token_required
def update_bug(bug_id):
    """
    General-purpose edit of title/description/severity/priority.
    - Admin can edit any bug, any of these fields.
    - Developer can edit the description of a bug ASSIGNED TO THEM
      (e.g. to add technical notes) but not title/severity/priority,
      since triage decisions belong to Admin.
    - Tester has no generic edit permission (they use /status instead).
    """
    supabase = current_app.config["SUPABASE_CLIENT"]
    bug = _get_bug_or_none(supabase, bug_id)
    if not bug:
        return error_response("Bug not found", 404)

    data = request.get_json(silent=True) or {}
    role = g.current_user["role"]
    updates = {}
    history_entries = []

    if role == "admin":
        if "title" in data:
            title = data["title"].strip()
            if len(title) < 3:
                return error_response("Bug title must be at least 3 characters", 400)
            updates["title"] = title
        if "description" in data:
            description = data["description"].strip()
            if len(description) < 10:
                return error_response("Bug description must be at least 10 characters", 400)
            updates["description"] = description
        if "severity" in data:
            if not is_valid_severity(data["severity"]):
                return error_response("Invalid severity value", 400)
            if data["severity"] != bug["severity"]:
                history_entries.append(("severity_changed", bug["severity"], data["severity"]))
            updates["severity"] = data["severity"]
        if "priority" in data:
            if not is_valid_priority(data["priority"]):
                return error_response("Invalid priority value", 400)
            if data["priority"] != bug["priority"]:
                history_entries.append(("priority_changed", bug["priority"], data["priority"]))
            updates["priority"] = data["priority"]

    elif role == "developer":
        if bug.get("assigned_to") != g.current_user["id"]:
            return error_response("You can only update bugs assigned to you", 403)
        if "description" in data:
            description = data["description"].strip()
            if len(description) < 10:
                return error_response("Bug description must be at least 10 characters", 400)
            updates["description"] = description
        # Silently ignore any other field a developer tries to send rather
        # than erroring, since the intent (editing notes) is still honored.

    else:
        return error_response("You do not have permission to perform this action", 403)

    if not updates:
        return error_response("No editable fields were provided", 400)

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = supabase.table("bugs").update(updates).eq("id", bug_id).execute()
    updated_bug = result.data[0]

    for action, old_value, new_value in history_entries:
        _record_history(supabase, bug_id, g.current_user["id"], action, old_value, new_value)

    return success_response("Bug updated successfully", {"bug": updated_bug})


@bugs_bp.route("/<bug_id>", methods=["DELETE"])
@token_required
@role_required("admin")
def delete_bug(bug_id):
    supabase = current_app.config["SUPABASE_CLIENT"]
    bug = _get_bug_or_none(supabase, bug_id)
    if not bug:
        return error_response("Bug not found", 404)

    supabase.table("bugs").delete().eq("id", bug_id).execute()
    return success_response("Bug deleted successfully")


@bugs_bp.route("/<bug_id>/assign", methods=["PUT"])
@token_required
@role_required("admin")
def assign_bug(bug_id):
    supabase = current_app.config["SUPABASE_CLIENT"]
    bug = _get_bug_or_none(supabase, bug_id)
    if not bug:
        return error_response("Bug not found", 404)

    data = request.get_json(silent=True) or {}
    developer_id = data.get("assigned_to")
    if not developer_id:
        return error_response("assigned_to (developer user id) is required", 400)

    dev_result = (
        supabase.table("users").select("id, role").eq("id", developer_id).limit(1).execute()
    )
    if not dev_result.data:
        return error_response("Assigned user not found", 404)
    if dev_result.data[0]["role"] != "developer":
        return error_response("Bugs can only be assigned to users with the developer role", 400)

    old_assignee = bug.get("assigned_to")
    result = (
        supabase.table("bugs")
        .update({"assigned_to": developer_id, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", bug_id)
        .execute()
    )
    updated_bug = result.data[0]

    _record_history(
        supabase, bug_id, g.current_user["id"], "assignment_changed", old_assignee, developer_id
    )

    return success_response("Bug assigned successfully", {"bug": updated_bug})


@bugs_bp.route("/<bug_id>/status", methods=["PUT"])
@token_required
def change_status(bug_id):
    supabase = current_app.config["SUPABASE_CLIENT"]
    bug = _get_bug_or_none(supabase, bug_id)
    if not bug:
        return error_response("Bug not found", 404)

    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if not new_status or not is_valid_status(new_status):
        return error_response(
            "A valid 'status' is required. Must be one of: Open, In Progress, "
            "Resolved, Closed, Reopened",
            400,
        )

    old_status = bug["status"]
    role = g.current_user["role"]

    # 1. Is this a legal move in the overall workflow at all?
    if not is_valid_status_transition(old_status, new_status):
        return error_response(
            f"Invalid status transition: cannot move from '{old_status}' to '{new_status}'",
            400,
        )

    # 2. Is this role allowed to make THIS particular move?
    allowed_moves = ROLE_STATUS_MOVES.get(role)
    if allowed_moves is not None and (old_status, new_status) not in allowed_moves:
        return error_response(
            "You do not have permission to perform this action", 403
        )

    # 3. Extra ownership check: a developer may only move bugs assigned to them.
    if role == "developer" and bug.get("assigned_to") != g.current_user["id"]:
        return error_response("You can only update bugs assigned to you", 403)

    result = (
        supabase.table("bugs")
        .update({"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", bug_id)
        .execute()
    )
    updated_bug = result.data[0]

    _record_history(supabase, bug_id, g.current_user["id"], "status_changed", old_status, new_status)

    return success_response("Bug status updated successfully", {"bug": updated_bug})


@bugs_bp.route("/<bug_id>/history", methods=["GET"])
@token_required
def get_bug_history(bug_id):
    supabase = current_app.config["SUPABASE_CLIENT"]
    bug = _get_bug_or_none(supabase, bug_id)
    if not bug:
        return error_response("Bug not found", 404)
    if not _can_view_bug(g.current_user, bug):
        return error_response("You do not have permission to view this bug's history", 403)

    result = (
        supabase.table("bug_history")
        .select("*, users(name, email)")
        .eq("bug_id", bug_id)
        .order("created_at", desc=False)
        .execute()
    )
    return success_response("Bug history retrieved", {"history": result.data})

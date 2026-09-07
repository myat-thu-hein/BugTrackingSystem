"""
app/routes/comments.py
------------------------
  POST /api/bugs/<bug_id>/comments  - add a comment to a bug
  GET  /api/bugs/<bug_id>/comments  - list comments on a bug

Registered under the same "/api/bugs" prefix as routes/bugs.py (see
app/__init__.py) so the final URLs match the spec exactly:
  /api/bugs/<id>/comments
"""

from flask import Blueprint, request, g, current_app

from app.middleware.auth import token_required
from app.utils.responses import success_response, error_response
from app.utils.validators import require_fields

comments_bp = Blueprint("comments", __name__)


def _get_bug_or_none(supabase, bug_id):
    result = supabase.table("bugs").select("*").eq("id", bug_id).limit(1).execute()
    return result.data[0] if result.data else None


def _can_view_bug(user, bug):
    if user["role"] in ("admin", "tester"):
        return True
    return bug.get("assigned_to") == user["id"]


@comments_bp.route("/<bug_id>/comments", methods=["POST"])
@token_required
def add_comment(bug_id):
    supabase = current_app.config["SUPABASE_CLIENT"]
    bug = _get_bug_or_none(supabase, bug_id)
    if not bug:
        return error_response("Bug not found", 404)
    if not _can_view_bug(g.current_user, bug):
        return error_response("You do not have permission to comment on this bug", 403)

    data = request.get_json(silent=True) or {}
    missing = require_fields(data, ["comment"])
    if missing:
        return error_response("A non-empty 'comment' field is required", 400)

    comment_text = data["comment"].strip()

    result = (
        supabase.table("comments")
        .insert({"bug_id": bug_id, "user_id": g.current_user["id"], "comment": comment_text})
        .execute()
    )
    return success_response("Comment added successfully", {"comment": result.data[0]}, 201)


@comments_bp.route("/<bug_id>/comments", methods=["GET"])
@token_required
def get_comments(bug_id):
    supabase = current_app.config["SUPABASE_CLIENT"]
    bug = _get_bug_or_none(supabase, bug_id)
    if not bug:
        return error_response("Bug not found", 404)
    if not _can_view_bug(g.current_user, bug):
        return error_response("You do not have permission to view comments on this bug", 403)

    result = (
        supabase.table("comments")
        .select("*, users(name, email, role)")
        .eq("bug_id", bug_id)
        .order("created_at", desc=False)
        .execute()
    )
    return success_response("Comments retrieved", {"comments": result.data})

"""
app/routes/users.py
---------------------
User management endpoints, mostly for Admins.

  GET /api/users               - list all users (admin only)
  GET /api/users/developers    - list developers (used to populate an
                                  "assign to" dropdown; any logged-in user
                                  may call this, since Testers/Admins both
                                  need it when assigning/reviewing bugs)
  PUT /api/users/<id>/role     - change a user's role (admin only)

Keeping this separate from auth.py mirrors the project structure in the
spec (routes/users.py) and keeps "manage accounts after they exist"
separate from "sign up / log in".
"""

from flask import Blueprint, request, current_app

from app.middleware.auth import token_required
from app.middleware.permissions import role_required
from app.utils.responses import success_response, error_response
from app.utils.validators import is_valid_role

users_bp = Blueprint("users", __name__)


@users_bp.route("", methods=["GET"])
@token_required
@role_required("admin")
def list_users():
    supabase = current_app.config["SUPABASE_CLIENT"]
    result = (
        supabase.table("users")
        .select("id, name, email, role, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return success_response("Users retrieved", {"users": result.data})


@users_bp.route("/developers", methods=["GET"])
@token_required
def list_developers():
    supabase = current_app.config["SUPABASE_CLIENT"]
    result = (
        supabase.table("users")
        .select("id, name, email")
        .eq("role", "developer")
        .order("name")
        .execute()
    )
    return success_response("Developers retrieved", {"developers": result.data})


@users_bp.route("/<user_id>/role", methods=["PUT"])
@token_required
@role_required("admin")
def update_user_role(user_id):
    supabase = current_app.config["SUPABASE_CLIENT"]
    data = request.get_json(silent=True) or {}
    new_role = data.get("role")

    if not is_valid_role(new_role):
        return error_response("role must be one of: admin, tester, developer", 400)

    existing = supabase.table("users").select("id").eq("id", user_id).limit(1).execute()
    if not existing.data:
        return error_response("User not found", 404)

    result = (
        supabase.table("users")
        .update({"role": new_role})
        .eq("id", user_id)
        .execute()
    )
    updated = result.data[0]
    return success_response(
        "User role updated",
        {
            "user": {
                "id": updated["id"],
                "name": updated["name"],
                "email": updated["email"],
                "role": updated["role"],
            }
        },
    )

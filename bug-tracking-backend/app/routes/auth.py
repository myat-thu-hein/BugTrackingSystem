"""
app/routes/auth.py
--------------------
Authentication endpoints:
  POST /api/auth/register  - create a new user account
  POST /api/auth/login     - verify credentials, return a JWT
  GET  /api/auth/me        - return the profile of the currently logged-in user

Security notes:
  - Passwords are hashed with werkzeug's generate_password_hash (PBKDF2-SHA256)
    before being stored. The plain password is never saved anywhere.
  - Password hashes are never included in any JSON response.
  - We deliberately IGNORE any "role" field sent by the client on register
    and default new accounts to "tester". An admin must promote users to
    "developer" or "admin" afterwards (see routes/users.py) - this stops a
    malicious user from registering themselves straight in as "admin".
"""

from flask import Blueprint, request, g, current_app
from werkzeug.security import generate_password_hash, check_password_hash

from app.middleware.auth import generate_token, token_required
from app.utils.responses import success_response, error_response
from app.utils.validators import is_valid_email, is_valid_password, require_fields

auth_bp = Blueprint("auth", __name__)


def _public_user(user_row):
    """Strip password_hash (and anything else internal) before returning a user."""
    return {
        "id": user_row["id"],
        "name": user_row["name"],
        "email": user_row["email"],
        "role": user_row["role"],
        "created_at": user_row.get("created_at"),
    }


@auth_bp.route("/register", methods=["POST"])
def register():
    supabase = current_app.config["SUPABASE_CLIENT"]
    data = request.get_json(silent=True) or {}

    missing = require_fields(data, ["name", "email", "password"])
    if missing:
        return error_response(f"Missing required field(s): {', '.join(missing)}", 400)

    name = data["name"].strip()
    email = data["email"].strip().lower()
    password = data["password"]

    if not is_valid_email(email):
        return error_response("Invalid email format", 400)

    if not is_valid_password(password):
        return error_response(
            "Password must be at least 8 characters and include a letter and a number",
            400,
        )

    # Check for an existing account with this email.
    existing = supabase.table("users").select("id").eq("email", email).limit(1).execute()
    if existing.data:
        return error_response("An account with this email already exists", 400)

    # NOTE: role is intentionally hard-coded to "tester" here - see module docstring.
    password_hash = generate_password_hash(password)
    insert_result = (
        supabase.table("users")
        .insert(
            {
                "name": name,
                "email": email,
                "password_hash": password_hash,
                "role": "tester",
            }
        )
        .execute()
    )

    if not insert_result.data:
        return error_response("Failed to create user", 500)

    new_user = insert_result.data[0]
    return success_response(
        "User registered successfully", {"user": _public_user(new_user)}, 201
    )


@auth_bp.route("/login", methods=["POST"])
def login():
    supabase = current_app.config["SUPABASE_CLIENT"]
    data = request.get_json(silent=True) or {}

    missing = require_fields(data, ["email", "password"])
    if missing:
        return error_response(f"Missing required field(s): {', '.join(missing)}", 400)

    email = data["email"].strip().lower()
    password = data["password"]

    result = supabase.table("users").select("*").eq("email", email).limit(1).execute()
    if not result.data:
        # Same generic message as a wrong password, so we don't leak which
        # emails are registered.
        return error_response("Invalid email or password", 401)

    user = result.data[0]
    if not check_password_hash(user["password_hash"], password):
        return error_response("Invalid email or password", 401)

    token = generate_token(user)
    return success_response(
        "Login successful",
        {"token": token, "user": _public_user(user)},
        200,
    )


@auth_bp.route("/me", methods=["GET"])
@token_required
def me():
    # g.current_user was already loaded fresh from the DB by @token_required
    # and already excludes password_hash.
    return success_response("Current user", {"user": g.current_user})

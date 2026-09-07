"""
app/middleware/auth.py
------------------------
Everything related to JWT tokens:
  - creating a token when a user logs in
  - decoding/validating a token on every protected request
  - a `@token_required` decorator that routes use to protect endpoints

How it fits together:
  routes/*.py  ->  uses @token_required  ->  this file verifies the JWT,
  loads the user row from Supabase, and stores it on `flask.g.current_user`
  so the route function can read `g.current_user["role"]`, etc.
"""

from functools import wraps
from datetime import datetime, timedelta, timezone

import jwt
from flask import request, g, current_app

from app.utils.responses import error_response


def generate_token(user):
    """Create a signed JWT for a user dict (must contain id, email, role)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(hours=current_app.config["JWT_EXPIRES_HOURS"]),
    }
    token = jwt.encode(
        payload,
        current_app.config["JWT_SECRET_KEY"],
        algorithm=current_app.config["JWT_ALGORITHM"],
    )
    # PyJWT >= 2 returns a str already; older versions return bytes.
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def decode_token(token):
    """Decode and validate a JWT. Raises jwt exceptions on failure."""
    return jwt.decode(
        token,
        current_app.config["JWT_SECRET_KEY"],
        algorithms=[current_app.config["JWT_ALGORITHM"]],
    )


def _extract_token_from_header():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip()


def token_required(f):
    """
    Decorator for protected routes.

    On success, sets:
      g.current_user = {"id": ..., "email": ..., "role": ..., "name": ...}
    On failure, returns a 401 JSON response and the wrapped function is
    never called.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token_from_header()
        if not token:
            return error_response("Missing or invalid Authorization header", 401)

        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return error_response("Token has expired, please log in again", 401)
        except jwt.InvalidTokenError:
            return error_response("Invalid token", 401)

        # Load the current user fresh from the database. This makes sure
        # that, e.g., a role change or deleted account takes effect
        # immediately instead of trusting stale data baked into the token.
        supabase = current_app.config["SUPABASE_CLIENT"]
        result = (
            supabase.table("users")
            .select("id, name, email, role, created_at")
            .eq("id", payload["sub"])
            .limit(1)
            .execute()
        )
        if not result.data:
            return error_response("User account no longer exists", 401)

        g.current_user = result.data[0]
        return f(*args, **kwargs)

    return decorated

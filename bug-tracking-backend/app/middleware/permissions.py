"""
app/middleware/permissions.py
-------------------------------
Role-based access control (RBAC). This decorator must always be used
AFTER @token_required, because it reads g.current_user which
token_required is responsible for setting.

Example:
    @bugs_bp.route("/bugs/<bug_id>/assign", methods=["PUT"])
    @token_required
    @role_required("admin")
    def assign_bug(bug_id):
        ...
"""

from functools import wraps
from flask import g

from app.utils.responses import error_response


def role_required(*allowed_roles):
    """Only allow the request through if g.current_user's role is in allowed_roles."""

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            current_user = getattr(g, "current_user", None)
            if not current_user:
                # Should never happen if @token_required ran first, but
                # guard against misuse/misordering of decorators.
                return error_response("Authentication required", 401)

            if current_user["role"] not in allowed_roles:
                return error_response(
                    "You do not have permission to perform this action", 403
                )
            return f(*args, **kwargs)

        return decorated

    return decorator

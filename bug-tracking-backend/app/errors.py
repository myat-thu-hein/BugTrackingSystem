"""
app/errors.py
---------------
API exceptions and the global error handlers that turn *every* failure into
the same JSON envelope the frontend expects:

    {"success": false, "message": "...", "errors": {...}}

Route and service code raises an exception instead of returning an error
tuple, so a helper like `get_viewable_bug()` can stop a request from any depth:

    bug = get_viewable_bug(bug_id)      # raises NotFoundError / ForbiddenError
    if not text:
        raise BadRequestError("A non-empty 'comment' field is required")
"""

from flask import current_app
from werkzeug.exceptions import HTTPException

from app.utils.responses import error_response


class ApiError(Exception):
    """An expected failure with a message that is safe to show the client."""

    status_code = 400

    def __init__(self, message, status_code=None, errors=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.errors = errors


class BadRequestError(ApiError):
    status_code = 400


class UnauthorizedError(ApiError):
    status_code = 401


class ForbiddenError(ApiError):
    status_code = 403

    def __init__(self, message="You do not have permission to perform this action", **kwargs):
        super().__init__(message, **kwargs)


class NotFoundError(ApiError):
    status_code = 404


class ConflictError(ApiError):
    status_code = 409


_HTTP_MESSAGES = {
    400: "Bad request",
    404: "Resource not found",
    405: "Method not allowed on this endpoint",
    413: "Request body is too large",
}


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(exc):
        return error_response(exc.message, exc.status_code, exc.errors)

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):
        message = _HTTP_MESSAGES.get(exc.code, exc.description or "Request failed")
        return error_response(message, exc.code or 500)

    @app.errorhandler(Exception)
    def handle_unexpected_exception(exc):
        # Log the real cause for developers; never leak internals to clients.
        current_app.logger.exception("Unhandled error: %s", exc)
        if is_permission_error(exc):
            return error_response(
                "The database refused access to a table (permission denied). Run "
                "sql/migrations/003_grant_service_role.sql in the Supabase SQL Editor, then check /api/health/setup.",
                500,
            )
        if is_connection_error(exc):
            return error_response("Couldn't reach the database just now. Please try again.", 503)
        if is_missing_schema_error(exc):
            # Safe to say and very actionable: the SQL migration wasn't run.
            return error_response(
                "The database is missing a table or column. Run the latest SQL migration in Supabase "
                "(see bug-tracking-backend/README.md), then check /api/health/setup.",
                500,
            )
        return error_response("Internal server error", 500)


# PostgreSQL: undefined_table / undefined_column; PostgREST: table/column not in schema cache.
_MISSING_SCHEMA_CODES = {"42P01", "42703", "PGRST204", "PGRST205"}


def is_permission_error(exc):
    """PostgreSQL insufficient_privilege, e.g. a table never GRANTed to service_role."""
    return getattr(exc, "code", None) == "42501" or "permission denied for table" in str(exc).lower()


def is_connection_error(exc):
    """Network trouble talking to Supabase (timeouts, resets): temporary, so 503 not 500."""
    try:
        import httpx
    except ImportError:  # pragma: no cover
        return False
    return isinstance(exc, httpx.TransportError)


def is_missing_schema_error(exc):
    code = getattr(exc, "code", None)
    text = str(exc).lower()
    return code in _MISSING_SCHEMA_CODES or "schema cache" in text or (
        "does not exist" in text and ("relation" in text or "column" in text)
    )

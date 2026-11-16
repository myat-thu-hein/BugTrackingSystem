"""
app/routes/notifications.py
-----------------------------
  GET /api/notifications               - your latest notifications (?limit=, ?unread=true)
  GET /api/notifications/unread-count  - number for the bell badge
  PUT /api/notifications/<id>/read     - mark one as read
  PUT /api/notifications/read-all      - mark all as read
  GET /api/notifications/stream        - LIVE: Server-Sent Events stream

The stream sends `event: notification` the moment one is created for you,
plus a comment line every 15 s to keep proxies from closing the connection.
It ends itself after a minute; the browser reconnects automatically
and re-syncs with GET /api/notifications, so nothing is ever missed.

SAFETY: a stream keeps one server thread busy for as long as it is open.
On a server that handles one request at a time (gunicorn's default "sync"
worker, e.g. a Render start command of just `gunicorn run:app`), an open
stream would block every other request until gunicorn killed the worker,
and the app failed with 5xx errors (the FAQ was the first thing to break).
So the stream only runs on a threaded/async server in a single process
(see `live_stream_supported`); otherwise it answers 503 straight away and
the browser falls back to checking for notifications every few seconds.
"""

import json
import queue
import time

from flask import Blueprint, Response, current_app, g, request

from app.errors import NotFoundError
from app.extensions import get_db
from app.middleware.auth import token_required
from app.services.notification_service import serialize_notification
from app.services.realtime import bus
from app.utils.request import first_row
from app.utils.responses import error_response, success_response
from app.utils.validators import is_valid_uuid

notifications_bp = Blueprint("notifications", __name__)

DEFAULT_LIMIT, MAX_LIMIT = 30, 100


def live_stream_supported(environ):
    """
    True when holding a request open is safe and live delivery reaches everyone:
      - wsgi.multithread: gthread / gevent / eventlet workers and Flask's dev
        server set it; gunicorn's single-threaded sync worker does not
      - not wsgi.multiprocess: with several worker processes, a notification
        created in one process can't reach a stream held by another
    """
    return bool(environ.get("wsgi.multithread")) and not environ.get("wsgi.multiprocess")


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@notifications_bp.route("", methods=["GET"])
@token_required
def list_notifications():
    try:
        limit = max(1, min(MAX_LIMIT, int(request.args.get("limit", DEFAULT_LIMIT))))
    except ValueError:
        limit = DEFAULT_LIMIT
    query = get_db().table("notifications").select("*").eq("user_id", g.current_user["id"])
    if request.args.get("unread") == "true":
        query = query.eq("is_read", False)
    rows = query.order("created_at", desc=True).limit(limit).execute().data
    return success_response(
        "Notifications retrieved",
        {"notifications": [serialize_notification(r) for r in rows], "unread_count": _unread_count()},
    )


def _unread_count():
    rows = (
        get_db().table("notifications").select("id").eq("user_id", g.current_user["id"]).eq("is_read", False).execute().data
    )
    return len(rows)


@notifications_bp.route("/unread-count", methods=["GET"])
@token_required
def unread_count():
    return success_response("Unread count", {"unread_count": _unread_count()})


@notifications_bp.route("/<notification_id>/read", methods=["PUT"])
@token_required
def mark_read(notification_id):
    if not is_valid_uuid(notification_id):
        raise NotFoundError("Notification not found")
    row = first_row(
        get_db()
        .table("notifications")
        .update({"is_read": True})
        .eq("id", notification_id)
        .eq("user_id", g.current_user["id"])  # you can only touch your own
        .execute(),
        "Notification not found",
    )
    return success_response("Marked as read", {"notification": serialize_notification(row), "unread_count": _unread_count()})


@notifications_bp.route("/read-all", methods=["PUT"])
@token_required
def mark_all_read():
    get_db().table("notifications").update({"is_read": True}).eq("user_id", g.current_user["id"]).eq("is_read", False).execute()
    return success_response("All notifications marked as read", {"unread_count": 0})


@notifications_bp.route("/stream", methods=["GET"])
@token_required
def stream():
    if not live_stream_supported(request.environ):
        current_app.logger.warning(
            "Live notifications are off: this server can't hold streams open safely. "
            "Use: gunicorn run:app --worker-class gthread --workers 1 --threads 32 --timeout 120"
        )
        return error_response("Live notifications are not available on this server; the app will check every few seconds instead", 503)

    user_id = g.current_user["id"]
    keepalive = current_app.config.get("SSE_KEEPALIVE_SECONDS", 15)
    max_age = current_app.config.get("SSE_MAX_SECONDS", 55)
    unread = _unread_count()

    def events():
        subscription = bus.subscribe(user_id)
        started = time.monotonic()
        try:
            yield "retry: 3000\n\n"  # browser reconnect delay
            yield _sse("ready", {"unread_count": unread})
            while time.monotonic() - started < max_age:
                try:
                    payload = subscription.get(timeout=keepalive)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(payload.get("event", "message"), payload)
        finally:
            bus.unsubscribe(user_id, subscription)

    return Response(
        events(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # don't let proxies buffer the stream
            "Connection": "keep-alive",
        },
    )

"""
app/services/supabase_http.py
-------------------------------
Make the Supabase client safe to use from many threads at once.

supabase-py's database client (postgrest) always opens ONE shared HTTP/2
connection. Our server handles requests in parallel threads (Flask's dev
server with threaded=True, gunicorn gthread), and every thread then reads
and writes that single connection at the same time. On Windows this fails
with:

    httpx.ReadError: [WinError 10035] A non-blocking socket operation
    could not be completed immediately

and random requests (often the first ones after a page loads) returned 500.

The fix is to talk to Supabase over HTTP/1.1. httpx then keeps a pool of
connections and gives each concurrent request its own, which is the normal,
thread-safe setup. The data and API are exactly the same.
"""

import httpx

_patched = False


def use_http1_for_postgrest():
    """Patch postgrest so every session it creates uses HTTP/1.1 (idempotent)."""
    global _patched
    if _patched:
        return
    from postgrest import SyncPostgrestClient

    original = SyncPostgrestClient.create_session

    def create_session(self, *args, **kwargs):
        # Let postgrest build its session (base URL, auth headers, timeout...),
        # then rebuild the same session without HTTP/2. Copying the settings
        # instead of re-implementing them keeps this working across versions.
        session = original(self, *args, **kwargs)
        if not isinstance(session, httpx.Client):
            return session
        http1 = type(session)(
            base_url=session.base_url,
            headers=session.headers,
            timeout=session.timeout,
            follow_redirects=session.follow_redirects,
            http2=False,
        )
        session.close()
        return http1

    SyncPostgrestClient.create_session = create_session
    _patched = True

"""
tests/fakes.py
----------------
A tiny in-memory stand-in for the Supabase client so the API can be tested
offline: no network, no credentials, runs in milliseconds.

It implements only the query surface this project uses:
  table(name).select(cols).eq().in_().order().limit().execute()
  table(name).insert(row).execute() / .update(values).eq() / .delete().eq()
including PostgREST-style embedded selects such as "*, users(name, email)".
"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_EMBED = re.compile(r"^(?:(\w+):)?(\w+)(?:!(\w+))?\((.*)\)$")


def _split_top_level(columns):
    parts, depth, current = [], 0, ""
    for ch in columns:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    return parts


class FakeSupabase:
    def __init__(self):
        self.tables = {
            name: []
            for name in (
                "projects", "users", "bugs", "comments", "bug_history",
                "notifications", "admin_requests", "faqs", "support_questions",
            )
        }
        self._tick = 0

    def table(self, name):
        return FakeQuery(self, name)

    def now(self):
        self._tick += 1  # strictly increasing so ordering is deterministic
        return (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self._tick)).isoformat()


class FakeAPIError(Exception):
    """Shaped like postgrest.exceptions.APIError for a table that doesn't exist."""

    def __init__(self, table):
        self.code = "PGRST205"
        super().__init__(f"Could not find the table 'public.{table}' in the schema cache")


class FakePermissionError(Exception):
    """Shaped like postgrest's APIError for a table service_role wasn't GRANTed."""

    def __init__(self, table):
        self.code = "42501"
        super().__init__(f"permission denied for table {table}")


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table_name = db, table
        self._op, self._payload = "select", None
        self._columns, self._filters = "*", []
        self._order, self._limit = None, None

    # --- builders ---
    def select(self, columns="*"):
        self._op, self._columns = "select", columns
        return self

    def insert(self, row):
        self._op, self._payload = "insert", row
        return self

    def update(self, values):
        self._op, self._payload = "update", values
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, column, value):
        self._filters.append(lambda r: r.get(column) == value)
        return self

    def in_(self, column, values):
        self._filters.append(lambda r: r.get(column) in set(values))
        return self

    def order(self, column, desc=False):
        self._order = (column, desc)
        return self

    def limit(self, count):
        self._limit = count
        return self

    # --- execution ---
    def execute(self):
        if self.table_name not in self.db.tables:
            raise FakeAPIError(self.table_name)
        if self.table_name in getattr(self.db, "denied", ()):
            raise FakePermissionError(self.table_name)
        rows = self.db.tables[self.table_name]
        matching = [r for r in rows if all(f(r) for f in self._filters)]

        if self._op == "insert":
            row = self._with_defaults(dict(self._payload))
            rows.append(row)
            return SimpleNamespace(data=[dict(row)])
        if self._op == "update":
            for r in matching:
                r.update(self._payload)
            return SimpleNamespace(data=[dict(r) for r in matching])
        if self._op == "delete":
            self.db.tables[self.table_name] = [r for r in rows if r not in matching]
            if self.table_name == "bugs":  # mimic ON DELETE CASCADE
                gone = {r["id"] for r in matching}
                for child in ("comments", "bug_history", "notifications"):
                    self.db.tables[child] = [r for r in self.db.tables[child] if r.get("bug_id") not in gone]
            return SimpleNamespace(data=[dict(r) for r in matching])

        if self._order:
            column, desc = self._order
            matching.sort(key=lambda r: r.get(column) or "", reverse=desc)
        if self._limit is not None:
            matching = matching[: self._limit]
        return SimpleNamespace(data=[self._project(r) for r in matching])

    def _with_defaults(self, row):
        row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("created_at", self.db.now())
        if self.table_name == "bugs":
            row.setdefault("status", "Open")
            row.setdefault("assigned_to", None)
            row.setdefault("updated_at", row["created_at"])
        return row

    def _project(self, row):
        out = {}
        for part in _split_top_level(self._columns):
            embed = _EMBED.match(part)
            if part == "*":
                out.update(row)
            elif embed:
                alias, table, fk, fields = embed.groups()
                fk = fk or "user_id"
                target = next((u for u in self.db.tables[table] if u["id"] == row.get(fk)), None)
                wanted = [f.strip() for f in fields.split(",")]
                out[alias or table] = {f: target.get(f) for f in wanted} if target else None
            else:
                out[part] = row.get(part)
        return out

"""
app/utils/validators.py
-------------------------
Central place for allowed values (roles, severities, priorities, statuses),
the status transition rules, and small validation helper functions.

Keeping these constants in one file means the auth routes, bug routes,
and tests all agree on exactly what a "valid" value looks like.
"""

import re

ROLES = ("admin", "tester", "developer")

SEVERITIES = ("Minor", "Major", "Critical", "Blocker")

PRIORITIES = ("Low", "Medium", "High", "Critical")

STATUSES = ("Open", "In Progress", "Resolved", "Closed", "Reopened")

# Map of current_status -> set of statuses it may legally move to.
STATUS_TRANSITIONS = {
    "Open": {"In Progress"},
    "In Progress": {"Resolved"},
    "Resolved": {"Closed", "Reopened"},
    "Reopened": {"In Progress"},
    "Closed": set(),  # closed is a terminal state
}

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email):
    return bool(email) and bool(EMAIL_REGEX.match(email))


def is_valid_password(password):
    """Minimum 8 characters, at least one letter and one number."""
    if not password or len(password) < 8:
        return False
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_letter and has_digit


def is_valid_role(role):
    return role in ROLES


def is_valid_severity(value):
    return value in SEVERITIES


def is_valid_priority(value):
    return value in PRIORITIES


def is_valid_status(value):
    return value in STATUSES


def is_valid_status_transition(old_status, new_status):
    """Returns True only if moving from old_status to new_status is allowed."""
    if old_status not in STATUS_TRANSITIONS:
        return False
    return new_status in STATUS_TRANSITIONS[old_status]


def require_fields(data, fields):
    """
    Returns a list of field names that are missing or empty/blank in `data`.
    Use like: missing = require_fields(request.json, ["title", "description"])
    """
    missing = []
    for field in fields:
        value = data.get(field) if data else None
        if value is None or (isinstance(value, str) and value.strip() == ""):
            missing.append(field)
    return missing

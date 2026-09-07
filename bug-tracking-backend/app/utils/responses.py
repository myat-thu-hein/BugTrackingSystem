"""
app/utils/responses.py
-----------------------
Small helpers so every endpoint in the app returns JSON in exactly the
same shape. This keeps the frontend team's life simple.
"""

from flask import jsonify


def success_response(message="Success", data=None, status_code=200):
    body = {"success": True, "message": message}
    if data is not None:
        body["data"] = data
    return jsonify(body), status_code


def error_response(message="An error occurred", status_code=400, errors=None):
    body = {"success": False, "message": message}
    if errors is not None:
        body["errors"] = errors
    return jsonify(body), status_code

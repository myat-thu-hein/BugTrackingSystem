"""
app/routes/support.py
-----------------------
Support chat box: FAQ answers per project, plus questions the FAQ couldn't
answer, which go to the project admins.

  GET    /api/support/faqs                    - FAQs, most asked first      (members)
  POST   /api/support/faqs/<id>/hit           - count that an FAQ was shown (members)
  POST   /api/support/faqs                    - add an FAQ                  (admin)
  PUT    /api/support/faqs/<id>               - edit an FAQ                 (admin)
  DELETE /api/support/faqs/<id>               - delete an FAQ               (admin)
  POST   /api/support/faqs/defaults           - add the starter FAQs        (admin)
  POST   /api/support/questions               - ask the admins              (members)
  GET    /api/support/questions               - open + recent questions     (admin) / your own (others)
  PUT    /api/support/questions/<id>/answer   - {"answer", "add_to_faq"}    (admin)

Matching a typed question to an FAQ happens in the browser (instant and
free); `hits` counts how often each answer helped, which ranks the
"most asked" suggestions.
"""

from datetime import datetime, timezone

from flask import Blueprint, g

from app.errors import BadRequestError, NotFoundError
from app.extensions import get_db
from app.middleware.auth import token_required
from app.middleware.permissions import project_required, role_required
from app.services.notification_service import NotificationType, notify, project_admin_ids
from app.services.project_service import seed_default_faqs
from app.services.user_service import fetch_user_names
from app.utils.request import first_row, json_body
from app.utils.responses import success_response
from app.utils.validators import ANSWER_MAX, QUESTION_MAX, clean_str, is_valid_uuid

support_bp = Blueprint("support", __name__)


def _text(data, field, label, max_length, min_length=3):
    value = clean_str(data.get(field))
    if not value or len(value) < min_length:
        raise BadRequestError(f"{label} must be at least {min_length} characters")
    if len(value) > max_length:
        raise BadRequestError(f"{label} must be at most {max_length} characters")
    return value


def _faq_fields(data):
    keywords = clean_str(data.get("keywords")) or ""
    return {
        "question": _text(data, "question", "Question", QUESTION_MAX),
        "answer": _text(data, "answer", "Answer", ANSWER_MAX),
        "keywords": keywords[:300],
    }


def _get_faq(faq_id):
    rows = (
        get_db().table("faqs").select("*").eq("id", faq_id).eq("project_id", g.current_user["project_id"]).limit(1).execute().data
        if is_valid_uuid(faq_id)
        else []
    )
    if not rows:
        raise NotFoundError("FAQ not found")
    return rows[0]


# --- FAQs ---------------------------------------------------------------------
@support_bp.route("/faqs", methods=["GET"])
@token_required
@project_required
def list_faqs():
    rows = get_db().table("faqs").select("*").eq("project_id", g.current_user["project_id"]).execute().data
    rows.sort(key=lambda r: (-(r.get("hits") or 0), r.get("created_at") or ""))
    return success_response("FAQs retrieved", {"faqs": rows})


@support_bp.route("/faqs/<faq_id>/hit", methods=["POST"])
@token_required
@project_required
def faq_hit(faq_id):
    faq = _get_faq(faq_id)
    get_db().table("faqs").update({"hits": (faq.get("hits") or 0) + 1}).eq("id", faq["id"]).execute()
    return success_response("Thanks for the feedback")


@support_bp.route("/faqs", methods=["POST"])
@token_required
@project_required
@role_required("admin")
def create_faq():
    row = first_row(
        get_db().table("faqs").insert({**_faq_fields(json_body()), "project_id": g.current_user["project_id"], "hits": 0}).execute()
    )
    return success_response("FAQ added", {"faq": row}, 201)


@support_bp.route("/faqs/defaults", methods=["POST"])
@token_required
@project_required
@role_required("admin")
def add_default_faqs():
    """
    Projects created before the help chat existed (e.g. the "Default Project"
    made by the database migration) start with an empty FAQ, so the chat can't
    answer anything. This adds the starter questions; existing ones are kept.
    """
    added = seed_default_faqs(g.current_user["project_id"])
    message = f"Added {len(added)} starter FAQ{'s' if len(added) != 1 else ''}" if added else "All starter FAQs are already there"
    return success_response(message, {"faqs": added}, 201 if added else 200)


@support_bp.route("/faqs/<faq_id>", methods=["PUT"])
@token_required
@project_required
@role_required("admin")
def update_faq(faq_id):
    faq = _get_faq(faq_id)
    row = first_row(get_db().table("faqs").update(_faq_fields(json_body())).eq("id", faq["id"]).execute())
    return success_response("FAQ updated", {"faq": row})


@support_bp.route("/faqs/<faq_id>", methods=["DELETE"])
@token_required
@project_required
@role_required("admin")
def delete_faq(faq_id):
    faq = _get_faq(faq_id)
    get_db().table("faqs").delete().eq("id", faq["id"]).execute()
    return success_response("FAQ deleted")


# --- questions for the admins -------------------------------------------------------
@support_bp.route("/questions", methods=["POST"])
@token_required
@project_required
def ask_question():
    user = g.current_user
    question = _text(json_body(), "question", "Question", QUESTION_MAX)
    row = first_row(
        get_db()
        .table("support_questions")
        .insert({"project_id": user["project_id"], "user_id": user["id"], "question": question, "status": "open"})
        .execute()
    )
    notify(
        project_admin_ids(user["project_id"]),
        NotificationType.SUPPORT_QUESTION,
        f"{user['name']} asked: \"{question[:100]}\"",
        link="/admin/help",
        email=(
            f"Support question from {user['name']}",
            f"{user['name']} asked a question the FAQ couldn't answer",
            f"\"{question}\"\n\nAnswer it on the Help Center page.",
        ),
    )
    return success_response("Your question was sent to the project admins", {"question": row}, 201)


@support_bp.route("/questions", methods=["GET"])
@token_required
@project_required
def list_questions():
    user = g.current_user
    query = get_db().table("support_questions").select("*").eq("project_id", user["project_id"])
    if user["role"] != "admin":
        query = query.eq("user_id", user["id"])
    rows = query.order("created_at", desc=True).limit(100).execute().data
    names = fetch_user_names(uid for r in rows for uid in (r["user_id"], r.get("answered_by")))
    questions = [
        {**r, "user_name": names.get(r["user_id"]), "answered_by_name": names.get(r.get("answered_by"))} for r in rows
    ]
    return success_response("Questions retrieved", {"questions": questions})


@support_bp.route("/questions/<question_id>/answer", methods=["PUT"])
@token_required
@project_required
@role_required("admin")
def answer_question(question_id):
    db = get_db()
    rows = (
        db.table("support_questions").select("*").eq("id", question_id).eq("project_id", g.current_user["project_id"]).limit(1).execute().data
        if is_valid_uuid(question_id)
        else []
    )
    if not rows:
        raise NotFoundError("Question not found")
    question = rows[0]

    data = json_body()
    answer = _text(data, "answer", "Answer", ANSWER_MAX)
    updated = first_row(
        db.table("support_questions")
        .update({
            "answer": answer,
            "status": "answered",
            "answered_by": g.current_user["id"],
            "answered_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", question["id"])
        .execute()
    )

    faq = None
    if data.get("add_to_faq"):
        faq = first_row(
            db.table("faqs")
            .insert({
                "project_id": question["project_id"],
                "question": question["question"][:QUESTION_MAX],
                "answer": answer,
                "keywords": "",
                "hits": 0,
            })
            .execute()
        )

    notify(
        [question["user_id"]],
        NotificationType.SUPPORT_ANSWERED,
        f"{g.current_user['name']} answered your question: \"{answer[:120]}\"",
        link="/notifications",
    )
    return success_response("Answer sent", {"question": updated, "faq": faq})

from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, session

from .db import execute_insert, execute_write, fetch_all, fetch_one
from .validation import validate_opportunity_payload

opportunities_bp = Blueprint("opportunities", __name__)


@opportunities_bp.get("")
def list_opportunities():
    admin_id = session.get("admin_id")
    if not admin_id:
        return jsonify({"message": "Authentication required."}), 401

    rows = fetch_all(
        """
        SELECT id, name, category, duration, start_date, description, skills,
               future_opportunities, max_applicants, created_at, updated_at
        FROM opportunities
        WHERE admin_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (admin_id,),
    )

    return jsonify({"opportunities": [_serialize_opportunity(row) for row in rows]}), 200


@opportunities_bp.post("")
def create_opportunity():
    admin_id = session.get("admin_id")
    if not admin_id:
        return jsonify({"message": "Authentication required."}), 401

    payload = request.get_json(silent=True) or {}
    errors, cleaned = validate_opportunity_payload(payload)
    if errors:
        return jsonify({"message": "Validation failed.", "errors": errors}), 400

    opportunity_id = execute_insert(
        """
        INSERT INTO opportunities
        (admin_id, name, category, duration, start_date, description, skills, future_opportunities, max_applicants)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            admin_id,
            cleaned["name"],
            cleaned["category"],
            cleaned["duration"],
            cleaned["start_date"],
            cleaned["description"],
            ",".join(cleaned["skills"]),
            cleaned["future_opportunities"],
            cleaned["max_applicants"],
        ),
    )

    row = fetch_one(
        """
        SELECT id, name, category, duration, start_date, description, skills,
               future_opportunities, max_applicants, created_at, updated_at
        FROM opportunities
        WHERE id = ? AND admin_id = ?
        """,
        (opportunity_id, admin_id),
    )
    opportunity = _serialize_opportunity(row)
    _log_opportunity_creation(admin_id, opportunity)

    return (
        jsonify(
            {
                "message": "Opportunity created successfully.",
                "opportunity": opportunity,
            }
        ),
        201,
    )


@opportunities_bp.put("/<int:opportunity_id>")
def update_opportunity(opportunity_id):
    admin_id = session.get("admin_id")
    if not admin_id:
        return jsonify({"message": "Authentication required."}), 401

    existing = _fetch_admin_opportunity(admin_id, opportunity_id)
    if not existing:
        return jsonify({"message": "Opportunity not found."}), 404

    payload = request.get_json(silent=True) or {}
    errors, cleaned = validate_opportunity_payload(payload)
    if errors:
        return jsonify({"message": "Validation failed.", "errors": errors}), 400

    execute_write(
        """
        UPDATE opportunities
        SET name = ?, category = ?, duration = ?, start_date = ?, description = ?,
            skills = ?, future_opportunities = ?, max_applicants = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND admin_id = ?
        """,
        (
            cleaned["name"],
            cleaned["category"],
            cleaned["duration"],
            cleaned["start_date"],
            cleaned["description"],
            ",".join(cleaned["skills"]),
            cleaned["future_opportunities"],
            cleaned["max_applicants"],
            opportunity_id,
            admin_id,
        ),
    )

    updated = _fetch_admin_opportunity(admin_id, opportunity_id)
    return (
        jsonify(
            {
                "message": "Opportunity updated successfully.",
                "opportunity": _serialize_opportunity(updated),
            }
        ),
        200,
    )


@opportunities_bp.delete("/<int:opportunity_id>")
def delete_opportunity(opportunity_id):
    admin_id = session.get("admin_id")
    if not admin_id:
        return jsonify({"message": "Authentication required."}), 401

    existing = _fetch_admin_opportunity(admin_id, opportunity_id)
    if not existing:
        return jsonify({"message": "Opportunity not found."}), 404

    execute_write(
        "DELETE FROM opportunities WHERE id = ? AND admin_id = ?",
        (opportunity_id, admin_id),
    )
    return jsonify({"message": "Opportunity deleted successfully."}), 200


def _serialize_opportunity(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "duration": row["duration"],
        "start_date": row["start_date"],
        "description": row["description"],
        "skills": [skill.strip() for skill in row["skills"].split(",") if skill.strip()],
        "future_opportunities": row["future_opportunities"],
        "max_applicants": row["max_applicants"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _fetch_admin_opportunity(admin_id, opportunity_id):
    return fetch_one(
        """
        SELECT id, name, category, duration, start_date, description, skills,
               future_opportunities, max_applicants, created_at, updated_at
        FROM opportunities
        WHERE id = ? AND admin_id = ?
        """,
        (opportunity_id, admin_id),
    )


def _log_opportunity_creation(admin_id, opportunity):
    log_path = Path(current_app.config["OPPORTUNITY_LOG_PATH"])
    if not log_path.is_absolute():
        log_path = Path(current_app.root_path).parent / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(
            f"{datetime.now(timezone.utc).isoformat()} "
            f"admin_id={admin_id} "
            f"opportunity_id={opportunity['id']} "
            f"name={opportunity['name']} "
            f"category={opportunity['category']} "
            f"start_date={opportunity['start_date']}\n"
        )

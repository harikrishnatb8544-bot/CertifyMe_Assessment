import sqlite3
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from secrets import token_urlsafe

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import execute_write, fetch_all, fetch_one
from .validation import (
    normalize_email,
    validate_forgot_password_payload,
    validate_login_payload,
    validate_signup_payload,
)

auth_bp = Blueprint("auth", __name__)
INVALID_LOGIN_MESSAGE = "Invalid email or password"
FORGOT_PASSWORD_MESSAGE = (
    "If an account with that email exists, a reset link has been generated."
)


@auth_bp.post("/signup")
def signup():
    payload = request.get_json(silent=True) or {}
    errors, cleaned = validate_signup_payload(payload)
    if errors:
        return (
            jsonify(
                {
                    "message": "Validation failed.",
                    "errors": errors,
                }
            ),
            400,
        )

    try:
        execute_write(
            """
            INSERT INTO admins (full_name, email, password_hash)
            VALUES (?, ?, ?)
            """,
            (
                cleaned["full_name"],
                normalize_email(cleaned["email"]),
                generate_password_hash(cleaned["password"]),
            ),
        )
    except sqlite3.IntegrityError:
        return (
            jsonify(
                {
                    "message": "An account with this email already exists.",
                    "errors": {
                        "email": "An account with this email already exists."
                    },
                }
            ),
            409,
        )

    return (
        jsonify(
            {
                "message": "Account created successfully. Please sign in."
            }
        ),
        201,
    )


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    errors, cleaned = validate_login_payload(payload)
    if errors:
        return jsonify({"message": "Validation failed.", "errors": errors}), 400

    admin = fetch_one(
        """
        SELECT id, full_name, email, password_hash
        FROM admins
        WHERE email = ?
        """,
        (normalize_email(cleaned["email"]),),
    )

    if not admin or not check_password_hash(admin["password_hash"], cleaned["password"]):
        return (
            jsonify(
                {
                    "message": INVALID_LOGIN_MESSAGE,
                    "errors": {"credentials": INVALID_LOGIN_MESSAGE},
                }
            ),
            401,
        )

    remember_me = bool(cleaned["remember_me"])
    session.clear()
    session["admin_id"] = admin["id"]
    session["admin_email"] = admin["email"]
    session["admin_name"] = admin["full_name"]
    session.permanent = remember_me
    if remember_me:
        session.modified = True

    return jsonify(
        {
            "message": "Login successful.",
            "admin": _serialize_admin(admin),
            "opportunities": _get_admin_opportunities(admin["id"]),
        }
    ), 200


@auth_bp.get("/session")
def get_session():
    admin_id = session.get("admin_id")
    if not admin_id:
        return jsonify({"authenticated": False}), 200

    admin = fetch_one(
        """
        SELECT id, full_name, email
        FROM admins
        WHERE id = ?
        """,
        (admin_id,),
    )
    if not admin:
        session.clear()
        return jsonify({"authenticated": False}), 200

    return jsonify(
        {
            "authenticated": True,
            "admin": _serialize_admin(admin),
            "opportunities": _get_admin_opportunities(admin["id"]),
        }
    ), 200


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"message": "Signed out successfully."}), 200


@auth_bp.post("/forgot-password")
def forgot_password():
    payload = request.get_json(silent=True) or {}
    errors, cleaned = validate_forgot_password_payload(payload)
    if errors:
        return jsonify({"message": "Validation failed.", "errors": errors}), 400

    admin = fetch_one(
        """
        SELECT id, email
        FROM admins
        WHERE email = ?
        """,
        (normalize_email(cleaned["email"]),),
    )

    if admin:
        reset_token = token_urlsafe(32)
        token_hash = _hash_reset_token(reset_token)
        expires_at = _utc_now() + current_app.config["RESET_TOKEN_LIFETIME"]
        expires_at_iso = _to_storage_timestamp(expires_at)

        execute_write(
            """
            INSERT INTO password_reset_tokens (admin_id, token_hash, expires_at)
            VALUES (?, ?, ?)
            """,
            (admin["id"], token_hash, expires_at_iso),
        )
        _log_reset_link(admin["email"], reset_token, expires_at_iso)

    return jsonify({"message": FORGOT_PASSWORD_MESSAGE}), 200


@auth_bp.get("/reset-password/<token>")
def verify_reset_link(token):
    token_row = fetch_one(
        """
        SELECT token_hash, expires_at, used_at
        FROM password_reset_tokens
        WHERE token_hash = ?
        """,
        (_hash_reset_token(token),),
    )

    if not token_row:
        return jsonify({"message": "This reset link is invalid."}), 404

    if token_row["used_at"]:
        return jsonify({"message": "This reset link has already been used."}), 400

    if _parse_storage_timestamp(token_row["expires_at"]) < _utc_now():
        return jsonify({"message": "This reset link has expired."}), 410

    return jsonify({"message": "Reset link is valid.", "valid": True}), 200


def _serialize_admin(admin):
    return {
        "id": admin["id"],
        "full_name": admin["full_name"],
        "email": admin["email"],
    }


def _get_admin_opportunities(admin_id):
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
    return [
        {
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
        for row in rows
    ]


def _hash_reset_token(token):
    return sha256(token.encode("utf-8")).hexdigest()


def _utc_now():
    return datetime.now(timezone.utc)


def _to_storage_timestamp(value):
    return value.isoformat()


def _parse_storage_timestamp(value):
    return datetime.fromisoformat(value)


def _log_reset_link(email, token, expires_at):
    log_path = Path(current_app.config["RESET_LINK_LOG_PATH"])
    if not log_path.is_absolute():
        log_path = Path(current_app.root_path).parent / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    reset_link = request.url_root.rstrip("/") + f"/api/auth/reset-password/{token}"
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(
            f"{_utc_now().isoformat()} email={email} expires_at={expires_at} link={reset_link}\n"
        )

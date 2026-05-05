import re

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_OPPORTUNITY_CATEGORIES = {
    "technology",
    "business",
    "design",
    "marketing",
    "data",
    "other",
}


def normalize_email(email):
    return email.strip().lower()


def validate_signup_payload(payload):
    errors = {}
    cleaned = {
        "full_name": str(payload.get("full_name", "")).strip(),
        "email": str(payload.get("email", "")).strip(),
        "password": str(payload.get("password", "")),
        "confirm_password": str(payload.get("confirm_password", "")),
    }

    if not cleaned["full_name"]:
        errors["full_name"] = "Full name is required."

    if not cleaned["email"]:
        errors["email"] = "Email is required."
    elif not EMAIL_PATTERN.match(cleaned["email"]):
        errors["email"] = "Please enter a valid email address."

    if not cleaned["password"]:
        errors["password"] = "Password is required."
    elif len(cleaned["password"]) < 8:
        errors["password"] = "Password must be at least 8 characters."

    if not cleaned["confirm_password"]:
        errors["confirm_password"] = "Please confirm your password."
    elif cleaned["password"] != cleaned["confirm_password"]:
        errors["confirm_password"] = "Passwords must match."

    return errors, cleaned


def validate_login_payload(payload):
    errors = {}
    cleaned = {
        "email": str(payload.get("email", "")).strip(),
        "password": str(payload.get("password", "")),
        "remember_me": bool(payload.get("remember_me", False)),
    }

    if not cleaned["email"]:
        errors["email"] = "Email is required."
    elif not EMAIL_PATTERN.match(cleaned["email"]):
        errors["email"] = "Please enter a valid email address."

    if not cleaned["password"]:
        errors["password"] = "Password is required."

    return errors, cleaned


def validate_forgot_password_payload(payload):
    errors = {}
    cleaned = {
        "email": str(payload.get("email", "")).strip(),
    }

    if not cleaned["email"]:
        errors["email"] = "Email is required."
    elif not EMAIL_PATTERN.match(cleaned["email"]):
        errors["email"] = "Please enter a valid email address."

    return errors, cleaned


def validate_opportunity_payload(payload):
    errors = {}
    cleaned = {
        "name": str(payload.get("name", "")).strip(),
        "duration": str(payload.get("duration", "")).strip(),
        "start_date": str(payload.get("start_date", "")).strip(),
        "description": str(payload.get("description", "")).strip(),
        "skills": [str(skill).strip() for skill in payload.get("skills", []) if str(skill).strip()],
        "category": str(payload.get("category", "")).strip(),
        "future_opportunities": str(payload.get("future_opportunities", "")).strip(),
        "max_applicants": payload.get("max_applicants"),
    }

    if not cleaned["name"]:
        errors["name"] = "Opportunity name is required."
    if not cleaned["duration"]:
        errors["duration"] = "Duration is required."
    if not cleaned["start_date"]:
        errors["start_date"] = "Start date is required."
    if not cleaned["description"]:
        errors["description"] = "Description is required."
    if not cleaned["skills"]:
        errors["skills"] = "At least one skill is required."
    if not cleaned["category"]:
        errors["category"] = "Category is required."
    elif cleaned["category"].lower() not in ALLOWED_OPPORTUNITY_CATEGORIES:
        errors["category"] = "Category must be one of: Technology, Business, Design, Marketing, Data Science, Other."
    if not cleaned["future_opportunities"]:
        errors["future_opportunities"] = "Future opportunities are required."

    if cleaned["max_applicants"] in ("", None):
        cleaned["max_applicants"] = None
    else:
        try:
            cleaned["max_applicants"] = int(cleaned["max_applicants"])
            if cleaned["max_applicants"] < 1:
                raise ValueError
        except (TypeError, ValueError):
            errors["max_applicants"] = "Maximum applicants must be a positive number."

    return errors, cleaned

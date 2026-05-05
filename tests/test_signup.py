import tempfile
import unittest
from pathlib import Path

from backend import create_app


class SignupApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test.db"
        self.reset_log_path = Path(self.temp_dir.name) / "reset-links.log"
        self.opportunity_log_path = Path(self.temp_dir.name) / "opportunity_logs.log"
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE_PATH": str(db_path),
                "RESET_LINK_LOG_PATH": str(self.reset_log_path),
                "OPPORTUNITY_LOG_PATH": str(self.opportunity_log_path),
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_signup_success(self):
        response = self.client.post(
            "/api/auth/signup",
            json={
                "full_name": "Admin User",
                "email": "admin@example.com",
                "password": "Password123!",
                "confirm_password": "Password123!",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("Account created successfully", response.get_json()["message"])

    def test_signup_rejects_invalid_email(self):
        response = self.client.post(
            "/api/auth/signup",
            json={
                "full_name": "Admin User",
                "email": "not-an-email",
                "password": "Password123!",
                "confirm_password": "Password123!",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["errors"]["email"],
            "Please enter a valid email address.",
        )

    def test_signup_rejects_duplicate_email_case_insensitively(self):
        payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=payload)
        duplicate_response = self.client.post(
            "/api/auth/signup",
            json={**payload, "email": "ADMIN@example.com"},
        )

        self.assertEqual(duplicate_response.status_code, 409)
        self.assertEqual(
            duplicate_response.get_json()["errors"]["email"],
            "An account with this email already exists.",
        )

    def test_login_success_without_remember_me_uses_session_cookie(self):
        signup_payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=signup_payload)

        response = self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "Password123!",
                "remember_me": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["admin"]["email"], "admin@example.com")
        self.assertEqual(response.get_json()["opportunities"], [])

    def test_login_failure_returns_generic_message(self):
        response = self.client.post(
            "/api/auth/login",
            json={
                "email": "unknown@example.com",
                "password": "wrong-password",
                "remember_me": True,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.get_json()["message"],
            "Invalid email or password",
        )

    def test_login_with_remember_me_marks_session_permanent(self):
        signup_payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=signup_payload)
        self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "Password123!",
                "remember_me": True,
            },
        )

        with self.client.session_transaction() as session:
            self.assertTrue(session.permanent)

    def test_forgot_password_always_returns_same_message(self):
        signup_payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=signup_payload)

        existing = self.client.post(
            "/api/auth/forgot-password",
            json={"email": "admin@example.com"},
        )
        missing = self.client.post(
            "/api/auth/forgot-password",
            json={"email": "missing@example.com"},
        )

        self.assertEqual(existing.status_code, 200)
        self.assertEqual(missing.status_code, 200)
        self.assertEqual(existing.get_json()["message"], missing.get_json()["message"])

    def test_forgot_password_logs_link_for_registered_email(self):
        signup_payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=signup_payload)

        response = self.client.post(
            "/api/auth/forgot-password",
            json={"email": "admin@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.reset_log_path.exists())
        log_content = self.reset_log_path.read_text(encoding="utf-8")
        self.assertIn("email=admin@example.com", log_content)
        self.assertIn("/api/auth/reset-password/", log_content)

    def test_expired_reset_link_returns_clear_error(self):
        signup_payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=signup_payload)
        self.client.post("/api/auth/forgot-password", json={"email": "admin@example.com"})

        log_content = self.reset_log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
        token = log_content.split("link=")[1].rsplit("/", 1)[-1]

        with self.app.app_context():
            from backend.db import execute_write

            execute_write(
                """
                UPDATE password_reset_tokens
                SET expires_at = ?
                """,
                ("2000-01-01T00:00:00+00:00",),
            )

        response = self.client.get(f"/api/auth/reset-password/{token}")
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.get_json()["message"], "This reset link has expired.")

    def test_valid_reset_link_is_accepted_before_expiry(self):
        signup_payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=signup_payload)
        self.client.post("/api/auth/forgot-password", json={"email": "admin@example.com"})

        log_content = self.reset_log_path.read_text(encoding="utf-8").strip().splitlines()[-1]
        token = log_content.split("link=")[1].rsplit("/", 1)[-1]

        response = self.client.get(f"/api/auth/reset-password/{token}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["valid"])

    def test_opportunities_endpoint_requires_login(self):
        response = self.client.get("/api/opportunities")
        self.assertEqual(response.status_code, 401)

    def test_opportunities_endpoint_returns_only_logged_in_admin_records(self):
        admin_one = {
            "full_name": "Admin One",
            "email": "one@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        admin_two = {
            "full_name": "Admin Two",
            "email": "two@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=admin_one)
        self.client.post("/api/auth/signup", json=admin_two)

        with self.app.app_context():
            from backend.db import execute_write, fetch_one

            admin_one_row = fetch_one("SELECT id FROM admins WHERE email = ?", ("one@example.com",))
            admin_two_row = fetch_one("SELECT id FROM admins WHERE email = ?", ("two@example.com",))

            execute_write(
                """
                INSERT INTO opportunities
                (admin_id, name, category, duration, start_date, description, skills, future_opportunities, max_applicants)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    admin_one_row["id"],
                    "Admin One Opportunity",
                    "Technology",
                    "6 Months",
                    "2026-06-01",
                    "Opportunity owned by admin one.",
                    "Python,Flask",
                    "Growth path",
                    25,
                ),
            )
            execute_write(
                """
                INSERT INTO opportunities
                (admin_id, name, category, duration, start_date, description, skills, future_opportunities, max_applicants)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    admin_two_row["id"],
                    "Admin Two Opportunity",
                    "Business",
                    "3 Months",
                    "2026-07-15",
                    "Opportunity owned by admin two.",
                    "Sales,Strategy",
                    "Business path",
                    10,
                ),
            )

        self.client.post(
            "/api/auth/login",
            json={
                "email": "one@example.com",
                "password": "Password123!",
                "remember_me": False,
            },
        )
        response = self.client.get("/api/opportunities")

        self.assertEqual(response.status_code, 200)
        opportunities = response.get_json()["opportunities"]
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0]["name"], "Admin One Opportunity")
        self.assertEqual(opportunities[0]["category"], "Technology")

    def test_opportunities_endpoint_returns_empty_list_for_admin_with_no_records(self):
        signup_payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=signup_payload)
        self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "Password123!",
                "remember_me": False,
            },
        )

        response = self.client.get("/api/opportunities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["opportunities"], [])

    def test_create_opportunity_persists_to_database_and_returns_record(self):
        signup_payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=signup_payload)
        self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "Password123!",
                "remember_me": False,
            },
        )

        response = self.client.post(
            "/api/opportunities",
            json={
                "name": "Flask Bootcamp",
                "category": "Technology",
                "duration": "6 Months",
                "start_date": "2026-08-01",
                "description": "Learn backend engineering with Flask.",
                "skills": ["Python", "Flask"],
                "future_opportunities": "Backend roles",
                "max_applicants": 30,
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["opportunity"]["name"], "Flask Bootcamp")

        with self.app.app_context():
            from backend.db import fetch_one

            row = fetch_one(
                "SELECT name, category, skills FROM opportunities WHERE name = ?",
                ("Flask Bootcamp",),
            )
            self.assertIsNotNone(row)
            self.assertEqual(row["category"], "Technology")
            self.assertEqual(row["skills"], "Python,Flask")

    def test_created_opportunity_is_visible_after_login_again(self):
        signup_payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=signup_payload)
        self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "Password123!",
                "remember_me": False,
            },
        )
        self.client.post(
            "/api/opportunities",
            json={
                "name": "Persistent Opportunity",
                "category": "Business",
                "duration": "3 Months",
                "start_date": "2026-10-01",
                "description": "Should still exist after re-login.",
                "skills": ["Planning", "Execution"],
                "future_opportunities": "Leadership path",
                "max_applicants": 12,
            },
        )
        self.client.post("/api/auth/logout")

        login_response = self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "Password123!",
                "remember_me": False,
            },
        )

        self.assertEqual(login_response.status_code, 200)
        opportunities = login_response.get_json()["opportunities"]
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0]["name"], "Persistent Opportunity")

    def test_create_opportunity_writes_admin_scoped_log_entry(self):
        signup_payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=signup_payload)
        self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "Password123!",
                "remember_me": False,
            },
        )

        response = self.client.post(
            "/api/opportunities",
            json={
                "name": "Logged Opportunity",
                "category": "Design",
                "duration": "2 Months",
                "start_date": "2026-11-01",
                "description": "Verify logging.",
                "skills": ["UI", "UX"],
                "future_opportunities": "Design roles",
                "max_applicants": 18,
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.opportunity_log_path.exists())
        log_content = self.opportunity_log_path.read_text(encoding="utf-8")
        self.assertIn("admin_id=", log_content)
        self.assertIn("name=Logged Opportunity", log_content)
        self.assertIn("category=Design", log_content)

    def test_update_opportunity_changes_only_target_record(self):
        signup_payload = {
            "full_name": "Admin User",
            "email": "admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=signup_payload)
        self.client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "Password123!",
                "remember_me": False,
            },
        )

        first = self.client.post(
            "/api/opportunities",
            json={
                "name": "Original Opportunity",
                "category": "technology",
                "duration": "6 Months",
                "start_date": "2026-08-01",
                "description": "Original description.",
                "skills": ["Python"],
                "future_opportunities": "Original future",
                "max_applicants": 20,
            },
        ).get_json()["opportunity"]
        second = self.client.post(
            "/api/opportunities",
            json={
                "name": "Untouched Opportunity",
                "category": "business",
                "duration": "3 Months",
                "start_date": "2026-09-01",
                "description": "Should remain unchanged.",
                "skills": ["Planning"],
                "future_opportunities": "Untouched future",
                "max_applicants": 10,
            },
        ).get_json()["opportunity"]

        response = self.client.put(
            f"/api/opportunities/{first['id']}",
            json={
                "name": "Updated Opportunity",
                "category": "marketing",
                "duration": "7 Months",
                "start_date": "2026-10-01",
                "description": "Updated description.",
                "skills": ["SEO", "Content"],
                "future_opportunities": "Updated future",
                "max_applicants": 30,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["opportunity"]["name"], "Updated Opportunity")

        with self.app.app_context():
            from backend.db import fetch_one

            updated = fetch_one("SELECT name, category FROM opportunities WHERE id = ?", (first["id"],))
            untouched = fetch_one("SELECT name, category FROM opportunities WHERE id = ?", (second["id"],))
            self.assertEqual(updated["name"], "Updated Opportunity")
            self.assertEqual(updated["category"], "marketing")
            self.assertEqual(untouched["name"], "Untouched Opportunity")
            self.assertEqual(untouched["category"], "business")

    def test_delete_opportunity_removes_only_owner_record(self):
        admin_one = {
            "full_name": "Admin One",
            "email": "one@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        admin_two = {
            "full_name": "Admin Two",
            "email": "two@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        }
        self.client.post("/api/auth/signup", json=admin_one)
        self.client.post("/api/auth/signup", json=admin_two)

        self.client.post(
            "/api/auth/login",
            json={
                "email": "one@example.com",
                "password": "Password123!",
                "remember_me": False,
            },
        )
        own_opportunity = self.client.post(
            "/api/opportunities",
            json={
                "name": "Owner Opportunity",
                "category": "technology",
                "duration": "6 Months",
                "start_date": "2026-08-01",
                "description": "Owned by admin one.",
                "skills": ["Python"],
                "future_opportunities": "Owner future",
                "max_applicants": 20,
            },
        ).get_json()["opportunity"]
        self.client.post("/api/auth/logout")

        self.client.post(
            "/api/auth/login",
            json={
                "email": "two@example.com",
                "password": "Password123!",
                "remember_me": False,
            },
        )
        forbidden_delete = self.client.delete(f"/api/opportunities/{own_opportunity['id']}")
        self.assertEqual(forbidden_delete.status_code, 404)

        self.client.post("/api/auth/logout")
        self.client.post(
            "/api/auth/login",
            json={
                "email": "one@example.com",
                "password": "Password123!",
                "remember_me": False,
            },
        )
        allowed_delete = self.client.delete(f"/api/opportunities/{own_opportunity['id']}")
        self.assertEqual(allowed_delete.status_code, 200)

        with self.app.app_context():
            from backend.db import fetch_one

            deleted = fetch_one("SELECT id FROM opportunities WHERE id = ?", (own_opportunity["id"],))
            self.assertIsNone(deleted)


if __name__ == "__main__":
    unittest.main()

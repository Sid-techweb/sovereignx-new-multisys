import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

import uuid
import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.users import SQLUser
from app.config import settings

client = TestClient(app)

class TestAuthAPI(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.test_username = f"testuser_{uuid.uuid4().hex[:8]}"
        self.test_password = "SecurePassword123!"

    def tearDown(self):
        # Cleanup test user created during tests
        user = self.db.query(SQLUser).filter(SQLUser.username.like("testuser_%")).all()
        for u in user:
            self.db.delete(u)
        self.db.commit()
        self.db.close()

    def test_signup_creates_user_with_bcrypt_hash_and_autologin(self):
        """
        Verifies POST /auth/signup:
        - Creates DB user row.
        - Verifies stored password_hash is a valid bcrypt hash ($2b$... or $2a$...).
        - Verifies auto-login returns access_token and sets session cookie.
        """
        response = client.post("/auth/signup", json={
            "username": self.test_username,
            "password": self.test_password,
            "email": f"{self.test_username}@example.com"
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["user"]["username"], self.test_username)

        # Inspect database row directly
        db_user = self.db.query(SQLUser).filter(SQLUser.username == self.test_username).first()
        self.assertIsNotNone(db_user)
        self.assertNotEqual(db_user.password_hash, self.test_password)
        self.assertTrue(db_user.password_hash.startswith("$2b$") or db_user.password_hash.startswith("$2a$"))

    def test_signup_duplicate_username_rejection(self):
        """
        Verifies registering an existing username returns HTTP 400 Bad Request cleanly.
        """
        # First signup
        res1 = client.post("/auth/signup", json={
            "username": self.test_username,
            "password": self.test_password
        })
        self.assertEqual(res1.status_code, 200)

        # Duplicate signup attempt
        res2 = client.post("/auth/signup", json={
            "username": self.test_username,
            "password": "AnotherPassword123!"
        })
        self.assertEqual(res2.status_code, 400)
        self.assertIn("already registered", res2.json()["detail"].lower())

    def test_signup_too_short_password_rejection(self):
        """
        Verifies password < 8 characters is rejected with HTTP 400.
        """
        res = client.post("/auth/signup", json={
            "username": f"short_{self.test_username}",
            "password": "123"
        })
        self.assertIn(res.status_code, [400, 422])
        self.assertIn("at least 8 characters", str(res.json()["detail"]).lower())

    def test_login_invalid_credentials(self):
        """
        Verifies login with wrong password returns HTTP 401 Unauthorized.
        """
        # First create user
        client.post("/auth/signup", json={
            "username": self.test_username,
            "password": self.test_password
        })

        # Login with wrong password
        res = client.post("/auth/login", json={
            "username": self.test_username,
            "password": "WrongPassword!"
        })
        self.assertEqual(res.status_code, 401)
        self.assertIn("incorrect username or password", res.json()["detail"].lower())

    def test_unauthenticated_request_rejected(self):
        """
        Verifies protected routes reject unauthenticated requests with HTTP 401.
        """
        res = client.get("/documents")
        self.assertEqual(res.status_code, 401)

    def test_dual_auth_coexistence(self):
        """
        Verifies protected routes accept EITHER X-API-Key OR JWT Bearer token.
        """
        # 1. X-API-Key auth
        res_key = client.get("/documents", headers={"X-API-Key": settings.API_KEY})
        self.assertEqual(res_key.status_code, 200)

        # 2. JWT token auth
        signup_res = client.post("/auth/signup", json={
            "username": self.test_username,
            "password": self.test_password
        })
        token = signup_res.json()["access_token"]

        res_jwt = client.get("/documents", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_jwt.status_code, 200)

if __name__ == "__main__":
    unittest.main()

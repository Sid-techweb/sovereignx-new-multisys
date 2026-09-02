import os
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services import LocalDocumentStorage

MINIMAL_PDF = (
    b"%PDF-1.2\n"
    b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
    b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
    b"3 0 obj <</Type /Page /Parent 2 0 R /Resources <</Font <</F1 <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> >> >> /MediaBox [0 0 612 792] /Contents 4 0 R>> endobj\n"
    b"4 0 obj << /Length 51 >> stream\n"
    b"BT\n"
    b"/F1 12 Tf\n"
    b"70 700 Td\n"
    b"(Security Test Document) Tj\n"
    b"ET\n"
    b"endstream\n"
    b"endobj\n"
    b"xref\n"
    b"0 5\n"
    b"0000000000 65535 f\n"
    b"0000000009 00000 n\n"
    b"0000000062 00000 n\n"
    b"0000000117 00000 n\n"
    b"0000000228 00000 n\n"
    b"trailer << /Size 5 /Root 1 0 R >>\n"
    b"startxref\n"
    b"330\n"
    b"%%EOF"
)

class TestSecurityHardening(unittest.TestCase):
    def setUp(self):
        self.unauth_client = TestClient(app)
        self.auth_client = TestClient(app, headers={"X-API-Key": settings.API_KEY})

    def test_unauthenticated_request_rejected(self):
        """1. Protected endpoints reject requests with missing or invalid X-API-Key"""
        # Missing header -> 401
        res1 = self.unauth_client.get("/documents")
        self.assertEqual(res1.status_code, 401)
        self.assertEqual(res1.json()["detail"], "Invalid or missing API Key")

        # Invalid header -> 401
        res2 = self.unauth_client.get("/documents", headers={"X-API-Key": "invalid_key_xyz"})
        self.assertEqual(res2.status_code, 401)
        self.assertEqual(res2.json()["detail"], "Invalid or missing API Key")

    def test_authenticated_request_succeeds(self):
        """2. Protected endpoints accept valid X-API-Key header"""
        res = self.auth_client.get("/documents")
        self.assertEqual(res.status_code, 200)

    def test_public_endpoints_accessible_without_auth(self):
        """3. Public endpoints (/health, /api/sovereignty/status) remain accessible without auth"""
        health_res = self.unauth_client.get("/health")
        self.assertEqual(health_res.status_code, 200)

        sov_res = self.unauth_client.get("/api/sovereignty/status")
        self.assertEqual(sov_res.status_code, 200)

    def test_path_traversal_payload_prevention(self):
        """4. Test path traversal payload attack attempts on document storage"""
        temp_dir = tempfile.mkdtemp()
        try:
            storage = LocalDocumentStorage(base_path=temp_dir)
            files_dir = storage.files_path.resolve()

            # Test 1: Upload filename with path traversal sequence '../../etc/passwd.pdf'
            traversal_filename = "../../etc/passwd.pdf"
            path = storage._get_secure_path(traversal_filename)
            
            # Verify resolved path is strictly inside files_dir and basename was stripped
            self.assertTrue(path.resolve().is_relative_to(files_dir))
            self.assertEqual(path.name, "passwd.pdf")

            # Test 2: Endpoint level path traversal attempt
            res = self.auth_client.get("/documents/..%2F..%2Fetc%2Fpasswd/content")
            # Must return 400 Bad Request or 404 Not Found, never 200 or 500 file leak
            self.assertIn(res.status_code, [400, 404])
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

"""
Tests for the standalone worker FastAPI app (app/worker/main.py), driven
in-process via FastAPI's TestClient -- no real second process or socket
needed for these. Auth/contract tests need no Docker; execute-code's
success/timeout/network-block tests do (same pattern as
test_agent_tools.py's TestSandboxExecution).
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import settings
from app.worker.main import app
from app.worker.auth import NODE_KEY_HEADER

TEST_SECRET = "test-node-shared-secret-do-not-use-in-prod"


class TestWorkerHealth(unittest.TestCase):
    def test_health_is_unauthenticated_and_reports_role(self):
        client = TestClient(app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["role"], "worker")
        self.assertTrue(data["ready"])
        self.assertIn("node_id", data)

    def test_health_never_exposes_the_shared_secret(self):
        client = TestClient(app)
        with patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET):
            resp = client.get("/health")
        self.assertNotIn(TEST_SECRET, resp.text)


class TestWorkerAuth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_correct_secret_allowed(self):
        with patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET):
            resp = self.client.get("/capabilities", headers={NODE_KEY_HEADER: TEST_SECRET})
        self.assertEqual(resp.status_code, 200)

    def test_wrong_secret_rejected(self):
        with patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET):
            resp = self.client.get("/capabilities", headers={NODE_KEY_HEADER: "wrong-secret"})
        self.assertEqual(resp.status_code, 401)

    def test_missing_header_rejected(self):
        with patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET):
            resp = self.client.get("/capabilities")
        self.assertEqual(resp.status_code, 401)

    def test_server_with_no_secret_configured_refuses_execution(self):
        """An unset NODE_SHARED_SECRET must mean 'no execution possible',
        never 'anyone is trusted'."""
        with patch.object(settings, "NODE_SHARED_SECRET", ""):
            resp = self.client.get("/capabilities", headers={NODE_KEY_HEADER: "anything"})
        self.assertEqual(resp.status_code, 503)

    def test_execute_code_also_requires_auth(self):
        with patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET):
            resp = self.client.post("/execute-code", json={"language": "python", "code": "print(1)"})
        self.assertEqual(resp.status_code, 401)


class TestWorkerCapabilities(unittest.TestCase):
    def test_capabilities_only_advertises_implemented_ones(self):
        client = TestClient(app)
        with patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET):
            resp = client.get("/capabilities", headers={NODE_KEY_HEADER: TEST_SECRET})
        data = resp.json()
        self.assertIn("SANDBOX_EXECUTION", data["capabilities"])
        self.assertNotIn("VISION", data["capabilities"])
        self.assertNotIn("MODEL_INFERENCE", data["capabilities"])
        self.assertNotIn("GENERAL_CHAT", data["capabilities"])


class TestWorkerExecuteCodeContract(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self._secret_patch = patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET)
        self._secret_patch.start()
        self.headers = {NODE_KEY_HEADER: TEST_SECRET}

    def tearDown(self):
        self._secret_patch.stop()

    def test_rejects_non_python_language(self):
        resp = self.client.post("/execute-code", json={"language": "bash", "code": "echo hi"}, headers=self.headers)
        self.assertEqual(resp.status_code, 422)

    def test_rejects_shell_and_powershell(self):
        for lang in ("shell", "cmd", "powershell"):
            resp = self.client.post("/execute-code", json={"language": lang, "code": "x"}, headers=self.headers)
            self.assertEqual(resp.status_code, 422, f"expected rejection for language={lang}")

    def test_oversized_code_rejected(self):
        from app.worker.schemas import MAX_CODE_BYTES
        oversized = "x" * (MAX_CODE_BYTES + 1)
        resp = self.client.post("/execute-code", json={"language": "python", "code": oversized}, headers=self.headers)
        self.assertEqual(resp.status_code, 422)

    def test_timeout_seconds_bounded(self):
        resp = self.client.post(
            "/execute-code", json={"language": "python", "code": "print(1)", "timeout_seconds": 99999}, headers=self.headers
        )
        self.assertEqual(resp.status_code, 422)


class TestWorkerExecuteCodeSandbox(unittest.TestCase):
    """Real Docker invocations via the worker's HTTP contract."""

    def setUp(self):
        self.client = TestClient(app)
        self._secret_patch = patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET)
        self._secret_patch.start()
        self.headers = {NODE_KEY_HEADER: TEST_SECRET}

    def tearDown(self):
        self._secret_patch.stop()

    def test_successful_execution_returns_stdout(self):
        resp = self.client.post(
            "/execute-code", json={"language": "python", "code": "print('hello from worker')"}, headers=self.headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["exit_code"], 0)
        self.assertIn("hello from worker", data["stdout"])
        self.assertFalse(data["timed_out"])

    def test_timeout_is_enforced_and_no_orphan_container(self):
        import subprocess
        resp = self.client.post(
            "/execute-code",
            json={"language": "python", "code": "import time; time.sleep(30)", "timeout_seconds": 2},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["timed_out"])
        self.assertFalse(data["success"])
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=sovereignx-sandbox", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.stdout.strip(), "", "a sandbox container was left behind after a worker timeout")

    def test_network_is_blocked_even_via_worker(self):
        code = (
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('8.8.8.8', 53), timeout=3)\n"
            "    print('REACHED')\n"
            "except OSError as e:\n"
            "    print('BLOCKED', type(e).__name__)\n"
        )
        resp = self.client.post("/execute-code", json={"language": "python", "code": code}, headers=self.headers)
        data = resp.json()
        self.assertIn("BLOCKED", data["stdout"])
        self.assertNotIn("REACHED", data["stdout"])


if __name__ == "__main__":
    unittest.main()

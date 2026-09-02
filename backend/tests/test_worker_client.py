"""
Tests for WorkerClient (app/services/worker_client.py) against the REAL
worker FastAPI app (app/worker/main.py), run as a real background uvicorn
server on localhost -- genuine HTTP over a real socket, not an in-process
ASGI shortcut, so these tests exercise exactly the same code path the live
distributed acceptance test does. httpx's ASGITransport is async-only and
incompatible with WorkerClient's sync httpx.Client, which is why this uses
a real server rather than an in-process transport.
"""
import threading
import time
import unittest
from unittest.mock import patch

import httpx
import uvicorn

from app.config import settings
from app.worker.main import app as worker_app
from app.services.worker_client import (
    WorkerClient,
    WorkerAuthError,
    WorkerUnavailableError,
    WorkerExecutionError,
)

TEST_SECRET = "test-node-shared-secret-do-not-use-in-prod"
TEST_WORKER_HOST = "127.0.0.1"
TEST_WORKER_PORT = 18901
TEST_WORKER_URL = f"http://{TEST_WORKER_HOST}:{TEST_WORKER_PORT}"

_server = None
_thread = None


def setUpModule():
    global _server, _thread
    config = uvicorn.Config(worker_app, host=TEST_WORKER_HOST, port=TEST_WORKER_PORT, log_level="warning")
    _server = uvicorn.Server(config)
    _thread = threading.Thread(target=_server.run, daemon=True)
    _thread.start()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{TEST_WORKER_URL}/health", timeout=0.5)
            return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError("test worker server did not become ready in time")


def tearDownModule():
    if _server is not None:
        _server.should_exit = True
        _thread.join(timeout=5.0)


def _client_with(secret: str) -> WorkerClient:
    return WorkerClient(TEST_WORKER_URL, secret, connect_timeout_seconds=3.0, read_timeout_seconds=10.0)


class TestWorkerClientSuccess(unittest.TestCase):
    def test_health_reports_worker_identity(self):
        client = _client_with(TEST_SECRET)
        health = client.health()
        self.assertEqual(health.status, "healthy")
        self.assertTrue(health.ready)

    def test_capabilities_with_correct_secret(self):
        with patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET):
            caps = _client_with(TEST_SECRET).get_capabilities()
        self.assertIn("SANDBOX_EXECUTION", caps)

    def test_execute_code_success_shape_matches_local_sandbox(self):
        """Must return the same {stdout, stderr, exit_code, timed_out,
        elapsed_ms} shape as app.services.sandbox.execute_python_sandboxed,
        so callers can't tell local and remote results apart structurally."""
        with patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET):
            result = _client_with(TEST_SECRET).execute_code("print('remote hello')")
        self.assertEqual(set(result.keys()), {"stdout", "stderr", "exit_code", "timed_out", "elapsed_ms"})
        self.assertIn("remote hello", result["stdout"])
        self.assertEqual(result["exit_code"], 0)


class TestWorkerClientAuthFailure(unittest.TestCase):
    def test_wrong_secret_raises_worker_auth_error(self):
        with patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET):
            with self.assertRaises(WorkerAuthError):
                _client_with("wrong-secret").get_capabilities()

    def test_wrong_secret_on_execute_code_raises_worker_auth_error(self):
        with patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET):
            with self.assertRaises(WorkerAuthError):
                _client_with("wrong-secret").execute_code("print(1)")

    def test_server_secret_empty_raises_worker_auth_error(self):
        with patch.object(settings, "NODE_SHARED_SECRET", ""):
            with self.assertRaises(WorkerAuthError):
                _client_with("whatever").get_capabilities()


class TestWorkerClientUnreachable(unittest.TestCase):
    def test_connection_failure_raises_worker_unavailable_error(self):
        # A real network client pointed at a port nothing is listening on --
        # a genuine connection failure, not a simulated one.
        client = WorkerClient("http://127.0.0.1:1", TEST_SECRET, connect_timeout_seconds=1.0, read_timeout_seconds=1.0)
        with self.assertRaises(WorkerUnavailableError):
            client.health()

    def test_execute_code_unreachable_raises_worker_unavailable_error(self):
        client = WorkerClient("http://127.0.0.1:1", TEST_SECRET, connect_timeout_seconds=1.0, read_timeout_seconds=1.0)
        with self.assertRaises(WorkerUnavailableError):
            client.execute_code("print(1)")


class TestWorkerClientExecutionError(unittest.TestCase):
    def test_unsupported_language_raises_worker_execution_error(self):
        with patch.object(settings, "NODE_SHARED_SECRET", TEST_SECRET):
            with self.assertRaises(WorkerExecutionError):
                _client_with(TEST_SECRET).execute_code("echo hi", language="bash")


if __name__ == "__main__":
    unittest.main()

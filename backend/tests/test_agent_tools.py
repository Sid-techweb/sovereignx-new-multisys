"""
Tests for the agent's file I/O and sandboxed code-execution tools
(app/services/agent_tools.py, app/services/sandbox.py).

Path-safety tests are pure logic (fast, no Docker). Sandbox tests actually
invoke Docker -- real network-blocking/timeout/execution behavior, not
mocked -- so there are deliberately few of them (each costs real container
startup time), but they exercise the actual guarantee, not an assumption
about it.
"""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import settings


class TestAgentToolsPathSafety(unittest.TestCase):
    """No Docker involved -- pure path-resolution logic."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="sovereignx_test_storage_")
        self._original_storage_path = settings.DOCUMENT_STORAGE_PATH
        settings.DOCUMENT_STORAGE_PATH = str(Path(self._tmp) / "documents")

    def tearDown(self):
        settings.DOCUMENT_STORAGE_PATH = self._original_storage_path
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_write_then_read_round_trips(self):
        from app.services.agent_tools import write_file, read_file
        write_file("ws-1", "notes.txt", "hello world")
        result = read_file("ws-1", "notes.txt")
        self.assertEqual(result["content"], "hello world")

    def test_write_creates_parent_directories(self):
        from app.services.agent_tools import write_file, read_file
        write_file("ws-1", "data/readings/p101.csv", "temp,vib\n85,7\n")
        result = read_file("ws-1", "data/readings/p101.csv")
        self.assertIn("85,7", result["content"])

    def test_relative_path_traversal_blocked(self):
        from app.services.agent_tools import read_file, write_file
        write_file("ws-1", "safe.txt", "content")
        with self.assertRaises(ValueError):
            read_file("ws-1", "../../../etc/passwd")
        with self.assertRaises(ValueError):
            read_file("ws-1", "../ws-2/secret.txt")

    def test_absolute_path_rejected(self):
        from app.services.agent_tools import read_file, write_file
        with self.assertRaises(ValueError):
            write_file("ws-1", "C:\\Windows\\System32\\evil.txt", "x")
        with self.assertRaises(ValueError):
            read_file("ws-1", "/etc/passwd")

    def test_invalid_workspace_id_rejected(self):
        from app.services.agent_tools import write_file
        with self.assertRaises(ValueError):
            write_file("../escape", "file.txt", "x")
        with self.assertRaises(ValueError):
            write_file("ws with spaces/../..", "file.txt", "x")

    def test_workspaces_are_isolated_from_each_other(self):
        from app.services.agent_tools import write_file, read_file, list_files
        write_file("ws-a", "shared_name.txt", "content from A")
        write_file("ws-b", "shared_name.txt", "content from B")
        self.assertEqual(read_file("ws-a", "shared_name.txt")["content"], "content from A")
        self.assertEqual(read_file("ws-b", "shared_name.txt")["content"], "content from B")
        self.assertEqual(list_files("ws-a")["count"], 1)

    def test_read_nonexistent_file_raises(self):
        from app.services.agent_tools import read_file
        with self.assertRaises(ValueError):
            read_file("ws-1", "does_not_exist.txt")

    def test_oversized_content_rejected(self):
        from app.services.agent_tools import write_file
        from app.services import agent_tools
        with patch.object(agent_tools, "MAX_FILE_BYTES", 10):
            with self.assertRaises(ValueError):
                write_file("ws-1", "big.txt", "this is definitely more than 10 bytes")

    def test_list_files_reports_paths_and_sizes(self):
        from app.services.agent_tools import write_file, list_files
        write_file("ws-list", "a.txt", "12345")
        write_file("ws-list", "sub/b.txt", "1234567890")
        result = list_files("ws-list")
        paths = {f["path"] for f in result["files"]}
        self.assertEqual(paths, {"a.txt", "sub/b.txt"})
        sizes = {f["path"]: f["size_bytes"] for f in result["files"]}
        self.assertEqual(sizes["a.txt"], 5)
        self.assertEqual(sizes["sub/b.txt"], 10)


class TestToolRegistryAllowlisting(unittest.TestCase):
    """The tool registry only ever executes registered tools -- no arbitrary
    dynamic dispatch to unregistered names, and the new file/sandbox tools
    are actually registered under the expected names."""

    def test_unregistered_tool_name_rejected(self):
        from app.services.tools import LocalToolRegistry
        registry = LocalToolRegistry()
        resp = registry.execute("delete_everything", {}, context_id=None)
        self.assertEqual(resp.status, "failed")
        self.assertIn("not registered", resp.error)

    def test_new_agent_tools_are_registered(self):
        from app.services.tools import LocalToolRegistry
        registry = LocalToolRegistry()
        names = {t.name for t in registry.list_tools()}
        for expected in ("read_file", "write_file", "list_files", "execute_python"):
            self.assertIn(expected, names)

    def test_write_file_via_registry_enforces_path_safety(self):
        from app.services.tools import LocalToolRegistry
        registry = LocalToolRegistry()
        resp = registry.execute(
            "write_file",
            {"workspace_id": "ws-1", "path": "../../escape.txt", "content": "x"},
            context_id=None,
        )
        self.assertEqual(resp.status, "failed")


class TestSandboxExecution(unittest.TestCase):
    """Real Docker invocations -- deliberately few, each verifies an actual
    enforced guarantee rather than being mocked."""

    def test_basic_execution_returns_stdout(self):
        from app.services.sandbox import execute_python_sandboxed
        result = execute_python_sandboxed("print('hello'); print(1 + 1)")
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("hello", result["stdout"])
        self.assertIn("2", result["stdout"])

    def test_network_is_actually_blocked(self):
        from app.services.sandbox import execute_python_sandboxed
        result = execute_python_sandboxed(
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('8.8.8.8', 53), timeout=3)\n"
            "    print('REACHED')\n"
            "except OSError as e:\n"
            "    print('BLOCKED', type(e).__name__)\n"
        )
        self.assertIn("BLOCKED", result["stdout"])
        self.assertNotIn("REACHED", result["stdout"])

    def test_timeout_is_enforced_and_reported(self):
        from app.services.sandbox import execute_python_sandboxed
        result = execute_python_sandboxed("import time; time.sleep(30)", timeout_seconds=2)
        self.assertTrue(result["timed_out"])
        self.assertIsNone(result["exit_code"])

    def test_nonzero_exit_code_surfaced_not_raised(self):
        """A script that errors is a normal result, not an exception at this layer."""
        from app.services.sandbox import execute_python_sandboxed
        result = execute_python_sandboxed("raise ValueError('boom')")
        self.assertFalse(result["timed_out"])
        self.assertNotEqual(result["exit_code"], 0)
        self.assertIn("ValueError", result["stderr"])

    def test_execute_python_tool_wraps_sandbox_unavailable_as_tool_failure(self):
        from app.services import agent_tools
        with patch.object(agent_tools, "execute_python_sandboxed", side_effect=agent_tools.SandboxUnavailableError("docker down")):
            with self.assertRaises(ValueError):
                agent_tools.execute_python("print(1)")


if __name__ == "__main__":
    unittest.main()

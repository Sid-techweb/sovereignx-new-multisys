import os
import shutil
import tempfile
import json
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.services.tools import tool_registry

class TestLocalTools(unittest.TestCase):
    def setUp(self):
        # Setup temporary directories for testing logs/metadata storage
        self.test_dir = tempfile.mkdtemp()
        self.storage_patcher = unittest.mock.patch.object(settings, "DOCUMENT_STORAGE_PATH", os.path.join(self.test_dir, "storage"))
        self.storage_patcher.start()
        
        # Re-initialize path variables on tool_registry
        self.old_log_path = tool_registry.log_path
        tool_registry.log_path = Path(self.test_dir) / "logs" / "tool_executions.jsonl"
        tool_registry.log_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.client = TestClient(app, headers={"X-API-Key": settings.API_KEY})

    def tearDown(self):
        self.storage_patcher.stop()
        tool_registry.log_path = self.old_log_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_list_tools(self):
        """Test listing of all registered tools"""
        response = self.client.get("/tools")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # We expect our 3 tools
        self.assertEqual(len(data), 3)
        tool_names = [t["name"] for t in data]
        self.assertIn("compare_reading_against_sop_limit", tool_names)
        self.assertIn("compute_variance_across_readings", tool_names)
        self.assertIn("convert_units", tool_names)

    def test_compare_reading_sop_limit_exceeded(self):
        """Test exceedance limit tool with reading > limit"""
        payload = {
            "tool_name": "compare_reading_against_sop_limit",
            "arguments": {
                "reading_value": 91.0,
                "limit_value": 80.0,
                "comparison_type": "greater_than",
                "unit": "C"
            }
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["tool_name"], "compare_reading_against_sop_limit")
        outputs = data["outputs"]
        self.assertTrue(outputs["is_exceeded"])
        self.assertEqual(outputs["difference"], 11.0)
        self.assertEqual(outputs["percentage_exceeded"], 13.75)
        self.assertIn("Exceedance detected", outputs["summary"])

    def test_compare_reading_sop_limit_normal(self):
        """Test exceedance limit tool with normal reading"""
        payload = {
            "tool_name": "compare_reading_against_sop_limit",
            "arguments": {
                "reading_value": 75.0,
                "limit_value": 80.0,
                "comparison_type": "greater_than",
                "unit": "C"
            }
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["status"], "success")
        outputs = data["outputs"]
        self.assertFalse(outputs["is_exceeded"])
        self.assertEqual(outputs["difference"], 0.0)
        self.assertEqual(outputs["percentage_exceeded"], 0.0)
        self.assertIn("Normal operation", outputs["summary"])

    def test_compare_reading_less_than_limit(self):
        """Test exceedance limit tool with comparison_type='less_than'"""
        payload = {
            "tool_name": "compare_reading_against_sop_limit",
            "arguments": {
                "reading_value": 5.0,
                "limit_value": 6.0,
                "comparison_type": "less_than",
                "unit": "bar"
            }
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["status"], "success")
        outputs = data["outputs"]
        self.assertTrue(outputs["is_exceeded"])
        self.assertEqual(outputs["difference"], 1.0)
        self.assertAlmostEqual(outputs["percentage_exceeded"], 16.6667, places=4)

    def test_compute_variance_success(self):
        """Test variance statistics calculation tool"""
        payload = {
            "tool_name": "compute_variance_across_readings",
            "arguments": {
                "readings": [74.0, 78.5, 81.2, 91.0, 85.0]
            }
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["status"], "success")
        outputs = data["outputs"]
        self.assertEqual(outputs["count"], 5)
        self.assertEqual(outputs["mean"], 81.94)
        self.assertEqual(outputs["min"], 74.0)
        self.assertEqual(outputs["max"], 91.0)
        self.assertEqual(outputs["range"], 17.0)
        self.assertAlmostEqual(outputs["variance"], 41.718, places=3)
        self.assertAlmostEqual(outputs["std_dev"], 6.4589, places=3)

    def test_compute_variance_empty_list_fails(self):
        """Test variance stats tool fails on empty list input"""
        payload = {
            "tool_name": "compute_variance_across_readings",
            "arguments": {
                "readings": []
            }
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["status"], "failed")
        self.assertIn("empty list", data["error"].lower())

    def test_convert_units_temperature(self):
        """Test unit conversions for temperature"""
        # C to F
        payload = {
            "tool_name": "convert_units",
            "arguments": {"value": 100.0, "from_unit": "C", "to_unit": "F"}
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.json()["outputs"]["converted_value"], 212.0)

        # F to C
        payload = {
            "tool_name": "convert_units",
            "arguments": {"value": 32.0, "from_unit": "F", "to_unit": "C"}
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.json()["outputs"]["converted_value"], 0.0)

    def test_convert_units_pressure(self):
        """Test unit conversions for pressure"""
        # 10 bar to psi
        payload = {
            "tool_name": "convert_units",
            "arguments": {"value": 10.0, "from_unit": "bar", "to_unit": "psi"}
        }
        response = self.client.post("/tools/execute", json=payload)
        # 1 bar = 100,000 Pa, 1 psi = 6894.757 Pa -> 10 bar = 1,000,000 Pa / 6894.757 = 145.0377
        self.assertAlmostEqual(response.json()["outputs"]["converted_value"], 145.0377, places=2)

    def test_convert_units_incompatible_fails(self):
        """Test unit conversion fails when trying to convert C to bar"""
        payload = {
            "tool_name": "convert_units",
            "arguments": {"value": 10.0, "from_unit": "C", "to_unit": "bar"}
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.json()["status"], "failed")
        self.assertIn("incompatible", response.json()["error"].lower())

    def test_tool_logging_and_history(self):
        """Test that execution logs are written to the JSONL log file and can be queried"""
        # Perform 2 executions
        self.client.post("/tools/execute", json={
            "tool_name": "convert_units",
            "arguments": {"value": 0.0, "from_unit": "C", "to_unit": "F"}
        })
        self.client.post("/tools/execute", json={
            "tool_name": "compare_reading_against_sop_limit",
            "arguments": {"reading_value": 91.0, "limit_value": 80.0, "comparison_type": "greater_than"}
        })
        
        # Verify JSONL log file has entries
        self.assertTrue(tool_registry.log_path.exists())
        with open(tool_registry.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 2)
            
            entry1 = json.loads(lines[0])
            self.assertEqual(entry1["tool_name"], "convert_units")
            self.assertEqual(entry1["status"], "success")
            
            entry2 = json.loads(lines[1])
            self.assertEqual(entry2["tool_name"], "compare_reading_against_sop_limit")
            self.assertEqual(entry2["status"], "success")

        # Query endpoint `/tools/logs`
        response = self.client.get("/tools/logs?limit=10")
        self.assertEqual(response.status_code, 200)
        logs = response.json()
        self.assertEqual(len(logs), 2)
        # Should be in reversed order (newest first)
        self.assertEqual(logs[0]["tool_name"], "compare_reading_against_sop_limit")
        self.assertEqual(logs[1]["tool_name"], "convert_units")

    def test_invalid_parameters_failed_status(self):
        """Test that invalid types or missing parameters return a failed execution status"""
        # Missing argument
        payload = {
            "tool_name": "compare_reading_against_sop_limit",
            "arguments": {
                "reading_value": 91.0,
                "comparison_type": "greater_than"
            }
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.json()["status"], "failed")
        self.assertIn("missing required parameter", response.json()["error"].lower())

        # Invalid type
        payload = {
            "tool_name": "compare_reading_against_sop_limit",
            "arguments": {
                "reading_value": "not-a-float",
                "limit_value": 80.0,
                "comparison_type": "greater_than"
            }
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.json()["status"], "failed")
        self.assertIn("must be a float", response.json()["error"].lower())

    def test_compute_variance_oversized_list_fails(self):
        """Test that passing more than 10,000 readings is rejected"""
        oversized = [1.0] * 10001
        payload = {
            "tool_name": "compute_variance_across_readings",
            "arguments": {
                "readings": oversized
            }
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "failed")
        self.assertIn("maximum allowed size is 10,000 readings", data["error"])

    def test_execution_with_context_id(self):
        """Test that executing a tool with context_id propagates and logs it"""
        context_id = "CASE-001-investigation-001"
        payload = {
            "tool_name": "convert_units",
            "arguments": {"value": 0.0, "from_unit": "C", "to_unit": "F"},
            "context_id": context_id
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["context_id"], context_id)

        # Inspect the logs
        log_res = self.client.get("/tools/logs?limit=1")
        logs = log_res.json()
        self.assertEqual(logs[0]["context_id"], context_id)

    def test_execution_without_context_id(self):
        """Test that executing a tool without context_id records it as null"""
        payload = {
            "tool_name": "convert_units",
            "arguments": {"value": 0.0, "from_unit": "C", "to_unit": "F"}
        }
        response = self.client.post("/tools/execute", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIsNone(data["context_id"])

        # Inspect the logs
        log_res = self.client.get("/tools/logs?limit=1")
        logs = log_res.json()
        self.assertIsNone(logs[0]["context_id"])


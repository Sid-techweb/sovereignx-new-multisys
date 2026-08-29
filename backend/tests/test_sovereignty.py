import unittest
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.services.sovereignty import SovereigntyMonitor, TRUSTED_HOSTS

class TestSovereignty(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.monitor = SovereigntyMonitor()
        self.monitor.connections.clear()

    def test_localhost_connection_allowed(self):
        # Trigger an internal check by logging a mock localhost URL
        is_trusted = self.monitor.log_connection("GET", "http://localhost:11434/api/tags")
        self.assertTrue(is_trusted)
        
        summary = self.monitor.get_summary()
        self.assertEqual(summary["total_connections"], 1)
        self.assertEqual(summary["alerts"], 0)
        self.assertEqual(summary["status"], "NO EXTERNAL APPLICATION CONNECTIONS DETECTED")
        
        # Verify the details of the log entry
        entry = summary["log"][0]
        self.assertEqual(entry["host"], "localhost")
        self.assertEqual(entry["port"], 11434)
        self.assertEqual(entry["status"], "allowed")

    def test_external_connection_alerted(self):
        # Trigger an external check by logging a mock external URL
        is_trusted = self.monitor.log_connection("GET", "http://example.com/api/test")
        self.assertFalse(is_trusted)
        
        summary = self.monitor.get_summary()
        self.assertEqual(summary["total_connections"], 1)
        self.assertEqual(summary["alerts"], 1)
        self.assertEqual(summary["status"], "EXTERNAL APPLICATION CONNECTIONS DETECTED")
        
        # Verify details
        entry = summary["log"][0]
        self.assertEqual(entry["host"], "example.com")
        self.assertEqual(entry["port"], 80)
        self.assertEqual(entry["status"], "alert")

    def test_http_endpoint_status(self):
        # Log one allowed and one alert connection
        self.monitor.log_connection("POST", "http://127.0.0.1:11434/api/generate")
        self.monitor.log_connection("GET", "http://example.com/check")
        
        response = self.client.get("/api/sovereignty/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        filtered_logs = [log for log in data["log"] if log["host"] != "testserver"]
        self.assertEqual(len(filtered_logs), 2)
        self.assertEqual(data["alerts"], 1)
        self.assertEqual(data["status"], "EXTERNAL APPLICATION CONNECTIONS DETECTED")

    def test_interceptor_catches_client_calls(self):
        # The TestClient uses custom transport under the hood which communicates locally
        # Testing actual client calls via interceptor
        with httpx.Client() as client:
            try:
                # This call will fail if offline but the interceptor should still capture the attempt
                client.get("http://localhost:9999/dummy-endpoint", timeout=0.1)
            except Exception:
                pass
                
        summary = self.monitor.get_summary()
        self.assertTrue(len(summary["log"]) > 0)
        
        # At least one log entry should be localhost:9999
        found = False
        for entry in summary["log"]:
            if entry["host"] == "localhost" and entry["port"] == 9999:
                found = True
                self.assertEqual(entry["status"], "allowed")
        self.assertTrue(found, "Interceptor did not capture client call to localhost:9999")

import os
import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.api.reports import extract_unique_citations

class TestCasesAndReportsModule(unittest.TestCase):
    def setUp(self):
        self.unauth_client = TestClient(app)
        self.client = TestClient(app, headers={"X-API-Key": settings.API_KEY})

    def test_extract_unique_citations_reused_logic(self):
        """1. Test that Phase 8 extract_unique_citations correctly extracts citations"""
        answer = "Pump P-204 issue [Source: sensor.csv | chunk_id=c123] and SOP limit [Source: sop.pdf | page=2 | chunk_id=c456]."
        chunks = [
            {"chunk_id": "c123", "filename": "sensor.csv", "metadata": {"page_number": 1}},
            {"chunk_id": "c456", "filename": "sop.pdf", "metadata": {"page_number": 2}}
        ]
        formatted_answer, citations = extract_unique_citations(answer, chunks)
        
        self.assertIn("[1]", formatted_answer)
        self.assertIn("[2]", formatted_answer)
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0]["filename"], "sensor.csv")
        self.assertEqual(citations[0]["chunk_id"], "c123")
        self.assertEqual(citations[1]["filename"], "sop.pdf")
        self.assertEqual(citations[1]["page"], 2)

    def test_unauthenticated_cases_and_reports_rejected(self):
        """2. Test API key authentication enforcement on /cases and /reports"""
        res_cases = self.unauth_client.get("/cases")
        self.assertEqual(res_cases.status_code, 401)

        res_reports = self.unauth_client.get("/reports")
        self.assertEqual(res_reports.status_code, 401)

    def test_cases_crud_workflow(self):
        """3. Test Case creation, summary, detail, and manual status/severity updates"""
        # 1. Initial list
        get_res = self.client.get("/cases")
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertIn("summary", data)
        self.assertIn("cases", data)

        # 2. Create case
        payload = {
            "query": "What happened to Pump P-204?",
            "answer": "Temperature reached 91 C [Source: pump_P204_sensor_data.csv | chunk_id=c123].",
            "asset": "Pump P-204",
            "status": "Under Investigation",
            "severity": "High",
            "confidence": 0.85,
            "retrieved_chunks": [
                {"chunk_id": "c123", "filename": "pump_P204_sensor_data.csv", "metadata": {"page_number": 1}}
            ],
            "tool_executions": [
                {"tool_name": "compare_reading_against_sop_limit", "status": "success", "outputs": {"summary": "Exceedance detected"}}
            ]
        }
        create_res = self.client.post("/cases", json=payload)
        self.assertEqual(create_res.status_code, 201)
        c_data = create_res.json()
        
        case_id = c_data["case_id"]
        self.assertTrue(case_id.startswith("CASE-"))
        self.assertEqual(c_data["asset"], "Pump P-204")
        self.assertEqual(c_data["status"], "Under Investigation")
        self.assertEqual(c_data["severity"], "High")
        self.assertEqual(len(c_data["evidence"]), 1)
        self.assertEqual(c_data["evidence"][0]["filename"], "pump_P204_sensor_data.csv")

        # 3. Get detail
        detail_res = self.client.get(f"/cases/{case_id}")
        self.assertEqual(detail_res.status_code, 200)
        self.assertEqual(detail_res.json()["case_id"], case_id)

        # 4. Manual update status & severity (operator triggered)
        patch_res = self.client.patch(f"/cases/{case_id}", json={"status": "Resolved", "severity": "Low"})
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["status"], "Resolved")
        self.assertEqual(patch_res.json()["severity"], "Low")

    def test_reports_generation_and_download(self):
        """4. Test Report generation, listing, and file downloading"""
        investigate_payload = {
            "query": "What happened to Pump P-204?",
            "answer": "Temperature reached 91 C [Source: sensor.csv | chunk_id=c1].",
            "confidence": 0.9,
            "retrieved_chunks": [{"chunk_id": "c1", "filename": "sensor.csv", "metadata": {"page_number": 1}}],
            "tool_executions": [],
            "metadata": {"model_used": "qwen2.5:7b", "latency_ms": 100.0}
        }
        
        # 1. Generate DOCX
        docx_res = self.client.post("/reports/generate-docx", json=investigate_payload)
        self.assertEqual(docx_res.status_code, 200)
        self.assertIn("attachment", docx_res.headers.get("content-disposition", ""))

        # 2. Get list of reports
        list_res = self.client.get("/reports")
        self.assertEqual(list_res.status_code, 200)
        reports_data = list_res.json()
        self.assertGreaterEqual(reports_data["summary"]["total"], 1)

        # 3. Download generated file
        last_filename = reports_data["reports"][0]["filename"]
        dl_res = self.client.get(f"/reports/download/{last_filename}")
        self.assertEqual(dl_res.status_code, 200)

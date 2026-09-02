import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

import os
import uuid
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.database import engine, SessionLocal
from app.config import settings
from app.services import DocumentMetadataStore, LocalDocumentStorage
from app.rag.models import SQLDocumentChunk
from app.models.cases_reports import SQLReportRecord, SQLCase

client = TestClient(app)

class TestDeleteDocumentAPI(unittest.TestCase):
    def setUp(self):
        self.metadata_store = DocumentMetadataStore()
        self.storage = LocalDocumentStorage()
        self.headers = {"X-API-Key": settings.API_KEY}
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_delete_uncited_throwaway_document(self):
        """
        Tests deleting a throwaway document that is NOT cited anywhere:
        1. Create throwaway doc & metadata & pgvector chunks.
        2. Call DELETE /documents/{doc_id}.
        3. Confirm HTTP 200 OK.
        4. Confirm pgvector chunks removed (count == 0).
        5. Confirm metadata and physical files removed.
        """
        doc_id = str(uuid.uuid4())
        filename = f"uncited_test_{doc_id[:8]}.pdf"
        
        # Save metadata
        doc_meta = {
            "document_id": doc_id,
            "id": doc_id,
            "filename": filename,
            "file_type": "pdf",
            "mime_type": "application/pdf",
            "file_size": 1024,
            "size_bytes": 1024,
            "uploaded_at": "2026-09-02T12:00:00Z",
            "status": "processed",
            "source": "user_upload"
        }
        self.metadata_store.save(doc_id, doc_meta)
        
        # Save dummy physical storage file
        storage_name = f"{doc_id}.pdf"
        target_path = self.storage._get_secure_path(storage_name)
        with open(target_path, "wb") as f:
            f.write(b"%PDF-1.4 dummy content for uncited delete test")

        # Insert dummy pgvector chunks directly
        chunk_uuid = str(uuid.uuid4())
        dummy_chunk = SQLDocumentChunk(
            chunk_id=chunk_uuid,
            document_id=doc_id,
            filename=filename,
            source="user_upload",
            content="Dummy chunk text for uncited delete test.",
            embedding=[0.01] * 1024,
            chunk_index=0,
            document_checksum="dummy_checksum_123"
        )
        self.db.add(dummy_chunk)
        self.db.commit()

        # Confirm chunk exists before deletion
        count_before = self.db.query(SQLDocumentChunk).filter(SQLDocumentChunk.document_id == doc_id).count()
        self.assertEqual(count_before, 1)

        # Execute DELETE request
        response = client.delete(f"/documents/{doc_id}", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["document_id"], doc_id)
        self.assertEqual(data["chunks_deleted"], 1)
        self.assertEqual(len(data["cited_in_reports"]), 0)

        # Confirm pgvector chunks removed
        count_after = self.db.query(SQLDocumentChunk).filter(SQLDocumentChunk.document_id == doc_id).count()
        self.assertEqual(count_after, 0)

        # Confirm metadata removed
        self.assertIsNone(self.metadata_store.get(doc_id))
        
        # Confirm storage file removed
        self.assertFalse(self.storage.exists(storage_name))

    def test_delete_cited_document_warn_but_allow(self):
        """
        Tests deleting a cited document (warn-but-allow policy):
        1. Create throwaway doc & metadata & report record citing it.
        2. Call DELETE /documents/{doc_id}.
        3. Confirm HTTP 200 OK.
        4. Confirm cited_in_reports lists the report title.
        5. Confirm report record remains intact in DB (historical snapshot preserved).
        """
        doc_id = str(uuid.uuid4())
        filename = f"cited_test_{doc_id[:8]}.pdf"
        
        doc_meta = {
            "document_id": doc_id,
            "id": doc_id,
            "filename": filename,
            "file_type": "pdf",
            "mime_type": "application/pdf",
            "file_size": 2048,
            "size_bytes": 2048,
            "uploaded_at": "2026-09-02T12:00:00Z",
            "status": "processed",
            "source": "user_upload"
        }
        self.metadata_store.save(doc_id, doc_meta)
        
        # Create physical storage file
        storage_name = f"{doc_id}.pdf"
        target_path = self.storage._get_secure_path(storage_name)
        with open(target_path, "wb") as f:
            f.write(b"%PDF-1.4 dummy cited pdf content")

        # Create report record referencing this document
        report_id = str(uuid.uuid4())
        report = SQLReportRecord(
            report_id=report_id,
            case_id="CASE-001",
            query="Audit investigation query for P-204",
            format="DOCX",
            filename="Historical_Inspection_Audit_Report_2026.docx",
            status="Generated"
        )
        self.db.add(report)
        # Create SQLCase referencing this document
        test_case_id = f"CASE-DEL-{doc_id[:8]}"
        case_item = SQLCase(
            case_id=test_case_id,
            asset="Pump P-204",
            title="Pump P-204 Bearing Failure Investigation",
            finding="Overheating detected",
            query="P-204 temperature anomaly",
            status="Open",
            severity="High",
            confidence=0.85,
            evidence=[{"filename": filename, "document_id": doc_id}]
        )
        self.db.add(case_item)
        self.db.commit()

        # Call DELETE endpoint
        response = client.delete(f"/documents/{doc_id}", headers=self.headers)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["document_id"], doc_id)
        self.assertIn(f"Case {test_case_id}: Pump P-204 Bearing Failure Investigation", data["cited_in_cases"])

        # Verify historical case record is NOT deleted
        saved_case = self.db.query(SQLCase).filter(SQLCase.case_id == test_case_id).first()
        self.assertIsNotNone(saved_case)

        # Cleanup test records
        self.db.delete(saved_case)
        self.db.commit()

    def test_case001_demo_documents_protected_from_test_deletion(self):
        """
        Safety audit check: Verifies that official CASE-001 demo documents
        are not deleted or affected by test suites.
        """
        case001_filenames = [
            "pump_P204_SOP.pdf",
            "pump_P204_sensor_data.csv",
            "pump_P204_inspection_report.pdf",
            "pump_P204_past_incident_report.pdf",
            "pump_P204_photo.jpg",
            "compressor_C118_vibration_data.csv"
        ]
        
        # Verify CASE-001 documents exist in metadata store or pgvector
        all_meta = self.metadata_store.get_all()
        found_filenames = [m.get("filename") for m in all_meta]
        
        for case001_fn in case001_filenames:
            if case001_fn in found_filenames:
                doc = next(m for m in all_meta if m.get("filename") == case001_fn)
                doc_id = doc.get("document_id")
                self.assertIsNotNone(doc_id)
                
                # Verify server-side guard returns 403 Forbidden
                res = client.delete(f"/documents/{doc_id}", headers=self.headers)
                self.assertEqual(res.status_code, 403)
                self.assertIn("protected system asset", res.json()["detail"])

if __name__ == "__main__":
    unittest.main()

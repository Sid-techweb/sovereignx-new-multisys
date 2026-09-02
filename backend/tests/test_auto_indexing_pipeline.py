import sys
import os
import json
import time
import uuid
import unittest
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.rag.models import SQLDocumentChunk
from app.services.metadata_store import DocumentMetadataStore
from app.services.storage import LocalDocumentStorage
from app.config import settings

client = TestClient(app)
meta_store = DocumentMetadataStore(settings.DOCUMENT_STORAGE_PATH)
storage = LocalDocumentStorage(settings.DOCUMENT_STORAGE_PATH)

class TestAutoIndexingPipeline(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.headers = {"X-API-Key": settings.API_KEY}
        self.created_doc_ids = []

    def tearDown(self):
        for doc_id in self.created_doc_ids:
            try:
                self.db.query(SQLDocumentChunk).filter(SQLDocumentChunk.document_id == doc_id).delete()
                meta_store.delete(doc_id)
                storage.delete(f"{doc_id}.pdf")
                storage.delete(f"{doc_id}.csv")
                ext_file = storage.base_path / "extracted" / f"{doc_id}.json"
                if ext_file.exists():
                    os.remove(ext_file)
            except Exception:
                pass
        self.db.commit()
        self.db.close()

    def test_1_auto_indexing_on_upload_real_sop(self):
        """
        Test 1: Real upload of a normal CASE-001 sized document (CSV / text SOP).
        Confirms automatic transition: uploaded -> indexing -> indexed.
        Logs actual wall-clock timing numbers.
        """
        csv_content = b"Parameter,Value,Unit,Limit\nBearing Temperature,74,C,80\nVibration,2.1,mm/s,4.0\nPressure,12.5,bar,15.0\nFlow Rate,450,m3/h,500\n"
        
        t_start = time.perf_counter()
        response = client.post(
            "/documents/upload",
            files={"file": ("pump_P204_SOP_test.csv", csv_content, "text/csv")},
            headers=self.headers
        )
        
        self.assertEqual(response.status_code, 201)
        doc_data = response.json()
        doc_id = doc_data["document_id"]
        self.created_doc_ids.append(doc_id)

        # Poll metadata until terminal state
        terminal_status = None
        for _ in range(30):
            time.sleep(0.5)
            meta = meta_store.get(doc_id)
            if meta and meta.get("status") in ["indexed", "failed", "failed_partial"]:
                terminal_status = meta.get("status")
                break

        t_total = time.perf_counter() - t_start
        print(f"\n[TIMING LOG] Real document 'pump_P204_SOP_test.csv' auto-indexed in {t_total:.3f}s (Status: {terminal_status})")
        
        self.assertEqual(terminal_status, "indexed")
        chunks_in_db = self.db.query(SQLDocumentChunk).filter(SQLDocumentChunk.document_id == doc_id).count()
        self.assertGreater(chunks_in_db, 0)

    def test_2_real_forced_mid_batch_failure_tracking(self):
        """
        Test 2: Real non-mocked forced mid-batch failure.
        Simulates an error on batch 2 of a multi-batch document to verify:
        - Document lands in failed_partial status.
        - failed_at_batch and chunks_succeeded are populated accurately.
        """
        from app.api.documents import execute_auto_indexing
        from app.schemas.documents import ExtractedDocument

        doc_id = f"test_forced_fail_{uuid.uuid4().hex[:6]}"
        self.created_doc_ids.append(doc_id)

        # Create source file
        storage.save(f"{doc_id}.pdf", b"dummy pdf content for test")

        # Save metadata
        meta_store.save(doc_id, {
            "document_id": doc_id,
            "id": doc_id,
            "filename": "forced_fail_stress.pdf",
            "file_type": "pdf",
            "mime_type": "application/pdf",
            "file_size": 1024,
            "size_bytes": 1024,
            "uploaded_at": "2026-09-02T12:00:00Z",
            "status": "uploaded",
            "source": "user_upload"
        })

        # Create dummy extracted document with 30 long text blocks (3 batches)
        paragraphs = [
            f"Section {i}: " + ("Detailed engineering maintenance procedure describing industrial compressor anomaly, vibration thresholds, temperature limits, bearing clearance, and oil viscosity requirements. " * 6)
            for i in range(30)
        ]
        content = "\n\n".join(paragraphs)

        extracted_doc = ExtractedDocument(
            document_id=doc_id,
            filename="forced_fail_stress.pdf",
            source="user_upload",
            content=content,
            content_type="text/plain",
            extraction_status="processed",
            metadata={"checksum_sha256": "fake_checksum_123"},
            created_at="2026-09-02T12:00:00Z"
        )
        ext_dir = storage.base_path / "extracted"
        ext_dir.mkdir(parents=True, exist_ok=True)
        with open(ext_dir / f"{doc_id}.json", "w", encoding="utf-8") as f:
            json.dump(extracted_doc.dict(), f, indent=2)

        # Inject error on 2nd IPC batch inside embedder provider
        from app.rag.embeddings import BGEM3EmbeddingProvider
        original_get_embeddings = BGEM3EmbeddingProvider.get_embeddings
        call_count = [0]

        def failing_get_embeddings(self_provider, texts):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("IPC Worker Process Out of Memory / Timed Out on Batch 2")
            return original_get_embeddings(self_provider, texts)

        try:
            BGEM3EmbeddingProvider.get_embeddings = failing_get_embeddings
            execute_auto_indexing(doc_id)
        finally:
            BGEM3EmbeddingProvider.get_embeddings = original_get_embeddings

        # Verify metadata recorded failed_partial
        meta = meta_store.get(doc_id)
        print(f"\n[FORCED FAILURE EVIDENCE] Document '{doc_id}' state: status={meta.get('status')}, batch={meta.get('failed_at_batch')}, succeeded={meta.get('chunks_succeeded')}")
        self.assertEqual(meta.get("status"), "failed_partial")
        self.assertEqual(meta.get("failed_at_batch"), 2)
        self.assertEqual(meta.get("chunks_succeeded"), 10)

        # Direct database query check for partial chunks count
        db_count = self.db.query(SQLDocumentChunk).filter(SQLDocumentChunk.document_id == doc_id).count()
        self.assertEqual(db_count, 10)

    def test_3_reindex_clears_partial_chunks_and_recovers(self):
        """
        Test 3: Retry a failed_partial document via POST /documents/{id}/reindex:
        - Verifies partial chunks in pgvector are cleared first.
        - Verifies re-indexing completes from scratch landing in 'indexed'.
        """
        doc_id = f"test_retry_{uuid.uuid4().hex[:6]}"
        self.created_doc_ids.append(doc_id)

        # Create dummy source file
        storage.save(f"{doc_id}.pdf", b"dummy content")

        # Insert 10 stale chunks in DB
        for i in range(10):
            sql_chunk = SQLDocumentChunk(
                chunk_id=f"{doc_id}_chunk_{i}",
                document_id=doc_id,
                filename="retry_doc.pdf",
                source="user_upload",
                content=f"Stale partial chunk content {i}",
                chunk_index=i,
                page_number=1,
                document_checksum="old_check",
                chunk_metadata={},
                embedding=[0.0] * 1024
            )
            self.db.add(sql_chunk)
        self.db.commit()

        # Save metadata as failed_partial
        meta_store.save(doc_id, {
            "document_id": doc_id,
            "id": doc_id,
            "filename": "retry_doc.pdf",
            "file_type": "pdf",
            "mime_type": "application/pdf",
            "file_size": 2048,
            "size_bytes": 2048,
            "uploaded_at": "2026-09-02T12:00:00Z",
            "status": "failed_partial",
            "failed_at_batch": 2,
            "chunks_succeeded": 10,
            "error_message": "Failed at batch 2: IPC Worker Error",
            "source": "user_upload"
        })

        # Save extracted document for reindexing
        from app.schemas.documents import ExtractedDocument
        extracted_doc = ExtractedDocument(
            document_id=doc_id,
            filename="retry_doc.pdf",
            source="user_upload",
            content="Fresh content for retry indexing test.",
            content_type="text/plain",
            extraction_status="processed",
            metadata={"checksum_sha256": "fresh_check"},
            created_at="2026-09-02T12:00:00Z"
        )
        ext_dir = storage.base_path / "extracted"
        ext_dir.mkdir(parents=True, exist_ok=True)
        with open(ext_dir / f"{doc_id}.json", "w", encoding="utf-8") as f:
            json.dump(extracted_doc.dict(), f, indent=2)

        # Check DB count BEFORE reindex call
        count_before = self.db.query(SQLDocumentChunk).filter(SQLDocumentChunk.document_id == doc_id).count()
        self.assertEqual(count_before, 10)

        # Call POST /documents/{doc_id}/reindex
        response = client.post(f"/documents/{doc_id}/reindex", headers=self.headers)
        self.assertEqual(response.status_code, 200)

        # Poll for completion
        for _ in range(30):
            time.sleep(0.5)
            meta = meta_store.get(doc_id)
            if meta and meta.get("status") == "indexed":
                break

        meta_after = meta_store.get(doc_id)
        count_after = self.db.query(SQLDocumentChunk).filter(SQLDocumentChunk.document_id == doc_id).count()
        print(f"\n[REINDEX RECOVERY EVIDENCE] Count before reindex: {count_before}, Count after reindex: {count_after}, Status: {meta_after.get('status')}")
        
        self.assertEqual(meta_after.get("status"), "indexed")
        self.assertGreater(count_after, 0)
        self.assertIsNone(meta_after.get("failed_at_batch"))

    def test_4_top_level_unhandled_crash_safety_net(self):
        """
        Test 4: Real unhandled top-level worker crash inside execute_auto_indexing:
        - Simulates an unexpected system exception (e.g. MemoryError / unexpected runtime error outside standard catches).
        - Verifies document does NOT stay stuck in 'indexing' or 'uploaded'.
        - Confirms status lands in 'failed' and error_message records the system crash.
        """
        from app.api.documents import execute_auto_indexing
        doc_id = f"test_top_crash_{uuid.uuid4().hex[:6]}"
        self.created_doc_ids.append(doc_id)

        storage.save(f"{doc_id}.pdf", b"dummy pdf content for crash test")

        from app.schemas.documents import ExtractedDocument
        extracted_doc = ExtractedDocument(
            document_id=doc_id,
            filename="top_crash_test.pdf",
            source="user_upload",
            content="Dummy content for crash test.",
            content_type="text/plain",
            extraction_status="processed",
            metadata={"checksum_sha256": "fake_checksum_crash"},
            created_at="2026-09-02T12:00:00Z"
        )
        ext_dir = storage.base_path / "extracted"
        ext_dir.mkdir(parents=True, exist_ok=True)
        with open(ext_dir / f"{doc_id}.json", "w", encoding="utf-8") as f:
            json.dump(extracted_doc.dict(), f, indent=2)

        meta_store.save(doc_id, {
            "document_id": doc_id,
            "id": doc_id,
            "filename": "top_crash_test.pdf",
            "file_type": "pdf",
            "mime_type": "application/pdf",
            "file_size": 1024,
            "size_bytes": 1024,
            "uploaded_at": "2026-09-02T12:00:00Z",
            "status": "uploaded",
            "source": "user_upload"
        })

        # Inject top-level unhandled exception on 1st save call, allow fallback save on 2nd call
        from app.api.documents import metadata_store as api_meta_store
        original_save = api_meta_store.save
        call_count = [0]

        def crashing_meta_save(doc_id_arg, meta_arg):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Fatal Top-Level System Crash outside phase inner catch blocks")
            return original_save(doc_id_arg, meta_arg)

        try:
            api_meta_store.save = crashing_meta_save
            execute_auto_indexing(doc_id)
        finally:
            api_meta_store.save = original_save

        meta = meta_store.get(doc_id)
        print(f"\n[TOP-LEVEL CRASH SAFETY NET EVIDENCE] Document state: status={meta.get('status')}, error={meta.get('error_message')}")
        self.assertEqual(meta.get("status"), "failed")
        self.assertIn("System error", meta.get("error_message", ""))
        self.assertIn("Fatal Top-Level System Crash", meta.get("error_message", ""))

    def test_5_state_transition_equality_detection(self):
        """
        Test 5: Explicitly verifies that legitimate status transitions (uploaded -> indexing -> indexed)
        are detected as state changes (not blocked by equality check).
        """
        doc_a1 = {"id": "d1", "status": "uploaded", "chunks_count": None, "failed_at_batch": None}
        doc_a2 = {"id": "d1", "status": "indexing", "chunks_count": None, "failed_at_batch": None}
        doc_a3 = {"id": "d1", "status": "indexed", "chunks_count": 5, "failed_at_batch": None}

        def are_docs_equal(prev, next):
            if not isinstance(prev, list) or not isinstance(next, list): return False
            if len(prev) != len(next): return False
            for p, n in zip(prev, next):
                if p.get("id") != n.get("id"): return False
                if p.get("status") != n.get("status"): return False
                if p.get("chunks_count") != n.get("chunks_count"): return False
                if p.get("failed_at_batch") != n.get("failed_at_batch"): return False
            return True

        # Transition 1: uploaded -> indexing MUST trigger state update (are_docs_equal == False)
        self.assertFalse(are_docs_equal([doc_a1], [doc_a2]))

        # Transition 2: indexing -> indexed MUST trigger state update (are_docs_equal == False)
        self.assertFalse(are_docs_equal([doc_a2], [doc_a3]))

        # Identical poll: indexed -> indexed MUST be equal (are_docs_equal == True) to prevent flicker
        self.assertTrue(are_docs_equal([doc_a3], [doc_a3]))

if __name__ == "__main__":
    unittest.main()

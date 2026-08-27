import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services import LocalDocumentStorage, DocumentMetadataStore
from app.gateway.exceptions import UnsupportedProviderError

MINIMAL_PDF = (
    b"%PDF-1.2\n"
    b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
    b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
    b"3 0 obj <</Type /Page /Parent 2 0 R /Resources <</Font <</F1 <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> >> >> /MediaBox [0 0 612 792] /Contents 4 0 R>> endobj\n"
    b"4 0 obj << /Length 51 >> stream\n"
    b"BT\n"
    b"/F1 12 Tf\n"
    b"70 700 Td\n"
    b"(Pump P-204 Vibration is elevated) Tj\n"
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

MINIMAL_CSV = (
    b"Asset,Date,Pressure,Temperature,Vibration\n"
    b"Pump P-204,2026-08-12,8.4 bar,74 C,4.2 mm/s"
)

MINIMAL_IMAGE = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

class TestDocumentIntakeAndExtraction(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for document storage during tests
        self.test_dir = tempfile.mkdtemp()
        self.storage_patcher = patch.object(settings, "DOCUMENT_STORAGE_PATH", self.test_dir)
        self.storage_patcher.start()
        
        # Re-initialize local instances within tests to pick up the patched setting path
        from app.api.documents import storage as api_storage
        from app.api.documents import metadata_store as api_metadata_store
        api_storage.__init__(self.test_dir)
        api_metadata_store.__init__(self.test_dir)
        
        self.client = TestClient(app)

    def tearDown(self):
        self.storage_patcher.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_upload_valid_pdf_succeeds(self):
        """Test upload: Valid PDF upload succeeds"""
        response = self.client.post(
            "/documents/upload",
            files={"file": ("test_doc.pdf", MINIMAL_PDF, "application/pdf")}
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        
        # Verify schema elements
        self.assertIn("document_id", data)
        self.assertEqual(data["filename"], "test_doc.pdf")
        self.assertEqual(data["file_type"], "pdf")
        self.assertEqual(data["mime_type"], "application/pdf")
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["source"], "user_upload")

    def test_unsupported_file_extension_rejected(self):
        """Test file validation: Unsupported extension rejected"""
        response = self.client.post(
            "/documents/upload",
            files={"file": ("malicious.exe", b"executable content", "application/octet-stream")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file extension", response.json()["detail"])

    def test_invalid_mime_type_rejected(self):
        """Test file validation: Invalid MIME rejected where applicable"""
        response = self.client.post(
            "/documents/upload",
            files={"file": ("fake_sop.pdf", b"pdf content", "text/html")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("MIME type", response.json()["detail"])

    def test_oversized_file_rejected(self):
        """Test size validation: Oversized file rejected"""
        # Patch maximum upload size to 1MB and attempt to upload 2MB content
        with patch.object(settings, "MAX_UPLOAD_SIZE_MB", 1):
            large_content = b"a" * (2 * 1024 * 1024)
            response = self.client.post(
                "/documents/upload",
                files={"file": ("large_doc.pdf", large_content, "application/pdf")}
            )
            self.assertEqual(response.status_code, 413)
            self.assertIn("File size exceeds", response.json()["detail"])

    def test_path_traversal_protection(self):
        """Test path traversal: A malicious filename cannot escape directory"""
        response = self.client.post(
            "/documents/upload",
            files={"file": ("../../outside.pdf", MINIMAL_PDF, "application/pdf")}
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        
        # Stored filename must be UUID-based to prevent any directory breakout
        doc_id = data["document_id"]
        
        from app.api.documents import storage
        # The storage name is uuid.pdf
        storage_name = f"{doc_id}.pdf"
        
        # Verify the secure path resolution remains relative to files folder
        target_path = storage._get_secure_path(storage_name)
        self.assertTrue(target_path.is_relative_to(storage.files_path.resolve()))
        self.assertFalse("outside" in target_path.name)

    def test_uuid_storage_filename(self):
        """Test UUID storage: Stored filename does not equal original user filename"""
        response = self.client.post(
            "/documents/upload",
            files={"file": ("original_name.pdf", MINIMAL_PDF, "application/pdf")}
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        doc_id = data["document_id"]
        
        from app.api.documents import storage
        storage_name = f"{doc_id}.pdf"
        
        # Confirm that the file is stored under its UUID, not the original filename
        self.assertTrue(storage.exists(storage_name))
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "files", "original_name.pdf")))

    def test_checksum_generated(self):
        """Test Checksum: Uploaded file receives a valid SHA-256 checksum"""
        response = self.client.post(
            "/documents/upload",
            files={"file": ("doc.pdf", MINIMAL_PDF, "application/pdf")}
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("checksum_sha256", data)
        self.assertEqual(len(data["checksum_sha256"]), 64)  # 64 character hex string

    def test_pdf_extraction_succeeds(self):
        """Test PDF extraction: A small text-based PDF produces normalized text"""
        # 1. Upload PDF
        up_res = self.client.post(
            "/documents/upload",
            files={"file": ("pump_sop.pdf", MINIMAL_PDF, "application/pdf")}
        )
        doc_id = up_res.json()["document_id"]
        
        # 2. Trigger processing
        proc_res = self.client.post(f"/documents/{doc_id}/process")
        self.assertEqual(proc_res.status_code, 200)
        self.assertEqual(proc_res.json()["status"], "processed")
        
        # 3. Verify extracted content
        content_res = self.client.get(f"/documents/{doc_id}/content")
        self.assertEqual(content_res.status_code, 200)
        data = content_res.json()
        self.assertEqual(data["extraction_status"], "processed")
        self.assertIn("Pump P-204 Vibration is elevated", data["content"])

    def test_csv_extraction_succeeds(self):
        """Test CSV extraction: A small CSV produces deterministic normalized text"""
        # 1. Upload CSV
        up_res = self.client.post(
            "/documents/upload",
            files={"file": ("sensor.csv", MINIMAL_CSV, "text/csv")}
        )
        doc_id = up_res.json()["document_id"]
        
        # 2. Trigger processing
        proc_res = self.client.post(f"/documents/{doc_id}/process")
        self.assertEqual(proc_res.status_code, 200)
        self.assertEqual(proc_res.json()["status"], "processed")
        
        # 3. Verify content
        content_res = self.client.get(f"/documents/{doc_id}/content")
        data = content_res.json()
        self.assertEqual(data["extraction_status"], "processed")
        # Assert normalized form matches column mapping key-value layout
        self.assertIn("Asset: Pump P-204", data["content"])
        self.assertIn("Pressure: 8.4 bar", data["content"])
        self.assertIn("Temperature: 74 C", data["content"])

    @patch("transformers.Qwen2VLForConditionalGeneration.from_pretrained")
    @patch("transformers.AutoProcessor.from_pretrained")
    @patch("qwen_vl_utils.process_vision_info")
    def test_image_extraction_ocr_and_captioning(self, mock_process_vision, mock_processor_from_pretrained, mock_model_from_pretrained):
        """Test Image: Image processing performs OCR/captioning using Qwen2-VL"""
        import torch
        # Mock processor instance
        mock_processor = mock_processor_from_pretrained.return_value
        mock_processor.apply_chat_template.return_value = "dummy prompt"
        mock_processor.return_value = {"input_ids": torch.tensor([[1, 2, 3]])}
        mock_processor.batch_decode.return_value = ["Mocked Qwen2-VL visual description of Pump P-204."]
        
        # Mock model instance
        mock_model = mock_model_from_pretrained.return_value
        mock_model.parameters.return_value = iter([torch.nn.Parameter(torch.zeros(1))])
        mock_model.generate.return_value = torch.tensor([[1, 2, 3, 4, 5]])
        
        # Mock process_vision_info
        mock_process_vision.return_value = (None, None)

        # Reset singleton state of ImageExtractor
        from app.services.extractors import ImageExtractor
        ImageExtractor._model = None
        ImageExtractor._processor = None

        # 1. Upload image
        up_res = self.client.post(
            "/documents/upload",
            files={"file": ("diagram_pid.png", MINIMAL_IMAGE, "image/png")}
        )
        doc_id = up_res.json()["document_id"]
        
        # 2. Trigger processing
        proc_res = self.client.post(f"/documents/{doc_id}/process")
        self.assertEqual(proc_res.status_code, 200)
        self.assertEqual(proc_res.json()["status"], "processed")
        
        # 3. Verify content endpoint
        content_res = self.client.get(f"/documents/{doc_id}/content")
        data = content_res.json()
        self.assertEqual(data["extraction_status"], "processed")
        self.assertEqual(data["content"], "Mocked Qwen2-VL visual description of Pump P-204.")
        self.assertEqual(data["metadata"]["extraction_mode"], "pid_schematic_ocr")

    def test_processing_missing_document_returns_404(self):
        """Test Missing document: Processing nonexistent document returns HTTP 404"""
        response = self.client.post("/documents/non-existent-uuid/process")
        self.assertEqual(response.status_code, 404)

    def test_metadata_isolation(self):
        """Test Metadata isolation: GET /documents does not return full content"""
        # Upload doc
        self.client.post(
            "/documents/upload",
            files={"file": ("pump_sop.pdf", MINIMAL_PDF, "application/pdf")}
        )
        
        # Get list
        response = self.client.get("/documents")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # The list items should not hold a 'content' field
        for doc in data:
            self.assertNotIn("content", doc)

    def test_provenance_information_survives(self):
        """Test Provenance: document_id, filename, and source survive pipeline stages"""
        # 1. Upload
        up_res = self.client.post(
            "/documents/upload",
            files={"file": ("pump_sop.pdf", MINIMAL_PDF, "application/pdf")}
        )
        doc_id = up_res.json()["document_id"]
        
        # 2. Process
        self.client.post(f"/documents/{doc_id}/process")
        
        # 3. Content retrieval
        content_res = self.client.get(f"/documents/{doc_id}/content")
        data = content_res.json()
        
        self.assertEqual(data["document_id"], doc_id)
        self.assertEqual(data["filename"], "pump_sop.pdf")
        self.assertEqual(data["source"], "user_upload")

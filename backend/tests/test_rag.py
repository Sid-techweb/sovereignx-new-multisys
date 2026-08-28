import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
import numpy as np

from app.rag.chunker import chunk_document, split_text
from app.rag.embeddings import BGEM3EmbeddingProvider
from app.rag.exceptions import EmbeddingModelUnavailableError, IndexingError, SearchQueryError
from app.rag.indexer import KnowledgeBaseIndexer
from app.rag.retriever import KnowledgeBaseRetriever
from app.rag.models import SQLDocumentChunk, BGE_M3_DIMENSION
from app.schemas.documents import ExtractedDocument

class TestRAGChunker(unittest.TestCase):
    def test_split_text_deterministic(self):
        text = "This is a simple sample text. It has multiple words and sentences. It will be split."
        res1 = split_text(text, chunk_size=20, chunk_overlap=5)
        res2 = split_text(text, chunk_size=20, chunk_overlap=5)
        self.assertEqual(res1, res2)
        # Check that no chunk exceeds size
        for chunk in res1:
            self.assertTrue(len(chunk) <= 20)

    def test_chunk_document_provenance_and_ordering(self):
        doc_id = "test-uuid"
        filename = "test_doc.pdf"
        source = "user_upload"
        content = "Paragraph 1 is here.\n\nParagraph 2 is here. It is longer than paragraph 1.\n\nParagraph 3 is also here."
        metadata = {"page_count": 2}

        # Index page-level mapping since pdf with page_count
        chunks = chunk_document(doc_id, filename, source, content, metadata, chunk_size=30, chunk_overlap=5)
        
        self.assertTrue(len(chunks) > 0)
        # Verify provenance fields propagate
        for idx, chunk in enumerate(chunks):
            self.assertEqual(chunk.document_id, doc_id)
            self.assertEqual(chunk.filename, filename)
            self.assertEqual(chunk.source, source)
            self.assertEqual(chunk.chunk_index, idx)
            # PDF has pages, so page_number should be mapped
            self.assertIsNotNone(chunk.page_number)
            self.assertEqual(chunk.chunk_metadata.get("page_number"), chunk.page_number)
    def test_pdf_chunk_preserves_source_page(self):
        doc_id = "test-pdf-uuid"
        filename = "pump_P204_inspection_report.pdf"
        source = "user_upload"
        # 3 pages separated by the new separator
        content = "This is text from page 1.\n\n---SOVEREIGNX-PAGE-BREAK---\n\nThis is text from page 2.\n\n---SOVEREIGNX-PAGE-BREAK---\n\nThis is text from page 3."
        metadata = {"page_count": 3}

        chunks = chunk_document(doc_id, filename, source, content, metadata, chunk_size=50, chunk_overlap=10)
        
        # Verify page numbers mapping is exact
        page_1_chunks = [c for c in chunks if c.page_number == 1]
        page_2_chunks = [c for c in chunks if c.page_number == 2]
        page_3_chunks = [c for c in chunks if c.page_number == 3]
        
        self.assertTrue(len(page_1_chunks) > 0)
        self.assertTrue(len(page_2_chunks) > 0)
        self.assertTrue(len(page_3_chunks) > 0)
        
        self.assertIn("page 1", page_1_chunks[0].content)
        self.assertIn("page 2", page_2_chunks[0].content)
        self.assertIn("page 3", page_3_chunks[0].content)


class TestRAGEmbeddings(unittest.TestCase):
    @patch("sentence_transformers.sentence_transformer.modules.Transformer")
    @patch("sentence_transformers.sentence_transformer.modules.Pooling")
    @patch("sentence_transformers.SentenceTransformer")
    def test_bgem3_initializes_with_local_files_only(self, mock_transformer_cls, mock_pooling, mock_module_transformer_cls):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.get_embedding_dimension.return_value = 1024
        mock_transformer_cls.return_value = mock_model
        
        mock_transformer_instance = MagicMock()
        mock_transformer_instance.get_embedding_dimension.return_value = 1024
        mock_module_transformer_cls.return_value = mock_transformer_instance

        provider = BGEM3EmbeddingProvider()
        provider.initialize()

        # Check constructor arguments: model_kwargs={'local_files_only': True}
        mock_module_transformer_cls.assert_called_once_with("BAAI/bge-m3", model_kwargs={"local_files_only": True})
        self.assertTrue(provider._initialized)

    @patch("sentence_transformers.sentence_transformer.modules.Transformer")
    @patch("sentence_transformers.sentence_transformer.modules.Pooling")
    @patch("sentence_transformers.SentenceTransformer")
    def test_bgem3_dimension_mismatch_fails(self, mock_transformer_cls, mock_pooling, mock_module_transformer_cls):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 768  # Wrong dimension (pgvector expects 1024)
        mock_model.get_embedding_dimension.return_value = 768
        mock_transformer_cls.return_value = mock_model
        
        mock_transformer_instance = MagicMock()
        mock_transformer_instance.get_embedding_dimension.return_value = 768
        mock_module_transformer_cls.return_value = mock_transformer_instance

        provider = BGEM3EmbeddingProvider()
        with self.assertRaises(EmbeddingModelUnavailableError) as context:
            provider.initialize()
        self.assertIn("does not match database schema dimension", str(context.exception))

    @patch("sentence_transformers.sentence_transformer.modules.Transformer", side_effect=OSError("Model not found in cache"))
    def test_bgem3_fails_cleanly_when_offline_and_missing(self, mock_module_transformer_cls):
        provider = BGEM3EmbeddingProvider()
        with self.assertRaises(EmbeddingModelUnavailableError) as context:
            provider.initialize()
        
        self.assertIn("not available locally", str(context.exception))
        # Ensure constructor was still called with local_files_only=True
        mock_module_transformer_cls.assert_called_once_with("BAAI/bge-m3", model_kwargs={"local_files_only": True})

    @patch("sentence_transformers.sentence_transformer.modules.Transformer")
    @patch("sentence_transformers.sentence_transformer.modules.Pooling")
    @patch("sentence_transformers.SentenceTransformer")
    def test_embedding_generation_outputs(self, mock_transformer_cls, mock_pooling, mock_module_transformer_cls):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.get_embedding_dimension.return_value = 1024
        mock_model.encode.return_value = np.zeros(1024)
        mock_transformer_cls.return_value = mock_model
        
        mock_transformer_instance = MagicMock()
        mock_transformer_instance.get_embedding_dimension.return_value = 1024
        mock_module_transformer_cls.return_value = mock_transformer_instance

        provider = BGEM3EmbeddingProvider()
        emb = provider.get_embedding("Test sentence")
        
        self.assertEqual(len(emb), 1024)
        self.assertTrue(isinstance(emb[0], float))


class TestRAGIndexer(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.embedder = MagicMock()
        self.embedder.get_embeddings.return_value = [[0.1] * 1024]

    def test_index_document_succeeds(self):
        doc = ExtractedDocument(
            document_id="test-doc-id",
            filename="sop.pdf",
            source="user_upload",
            content="Grounded text content for SOP.",
            content_type="text",
            extraction_status="processed",
            metadata={"checksum_sha256": "fake-sha"},
            created_at="2026-08-26T12:00:00Z"
        )
        
        # Mock empty query for duplicate check
        self.db.query().filter().all.return_value = []

        indexer = KnowledgeBaseIndexer(self.db, self.embedder)
        chunk_count = indexer.index_document(doc)
        
        self.assertEqual(chunk_count, 1)
        self.db.add.assert_called_once()
        self.db.commit.assert_called_once()

    def test_index_unprocessed_rejected(self):
        doc = ExtractedDocument(
            document_id="test-doc-id",
            filename="diagram.png",
            source="user_upload",
            content="",
            content_type="text",
            extraction_status="not_implemented",
            metadata={},
            created_at="2026-08-26T12:00:00Z"
        )

        indexer = KnowledgeBaseIndexer(self.db, self.embedder)
        with self.assertRaises(IndexingError):
            indexer.index_document(doc)

    def test_stale_index_replaces_old_chunks(self):
        doc = ExtractedDocument(
            document_id="test-doc-id",
            filename="sop.pdf",
            source="user_upload",
            content="New content after SOP update.",
            content_type="text",
            extraction_status="processed",
            metadata={"checksum_sha256": "new-sha"},
            created_at="2026-08-26T12:00:00Z"
        )
        
        # Mock existing chunk with OLD checksum
        old_chunk = SQLDocumentChunk(
            chunk_id="old-chunk-id",
            document_id="test-doc-id",
            filename="sop.pdf",
            source="user_upload",
            content="Old content",
            chunk_index=0,
            document_checksum="old-sha"
        )
        self.db.query().filter().all.return_value = [old_chunk]

        indexer = KnowledgeBaseIndexer(self.db, self.embedder)
        chunk_count = indexer.index_document(doc)
        
        self.assertEqual(chunk_count, 1)
        # Should call delete queries
        self.db.query().filter().delete.assert_called_once()


class TestRAGRetriever(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        self.embedder = MagicMock()
        self.embedder.get_embedding.return_value = [0.1] * 1024

    def test_retrieve_query_returns_top_k(self):
        # Mock query return values
        chunk = SQLDocumentChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            filename="pump_sop.pdf",
            source="user_upload",
            content="Pump details.",
            chunk_index=0,
            page_number=1,
            chunk_metadata={}
        )
        
        # pgvector query mock returns list of (chunk, score)
        self.db.query().order_by().limit().all.return_value = [(chunk, 0.85)]

        retriever = KnowledgeBaseRetriever(self.db, self.embedder)
        results, below_threshold = retriever.retrieve("pump vibration", top_k=3)

        self.assertEqual(len(results), 1)
        self.assertFalse(below_threshold)
        self.assertEqual(results[0]["filename"], "pump_sop.pdf")
        self.assertEqual(results[0]["score"], 0.85)
        self.assertEqual(results[0]["metadata"]["page_number"], 1)

    def test_retrieve_below_threshold_returns_empty_and_flag(self):
        chunk = SQLDocumentChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            filename="pump_sop.pdf",
            source="user_upload",
            content="Pump details.",
            chunk_index=0,
            page_number=1,
            chunk_metadata={}
        )
        
        # pgvector query mock returns list of (chunk, score) below threshold
        self.db.query().order_by().limit().all.return_value = [(chunk, 0.45)]

        retriever = KnowledgeBaseRetriever(self.db, self.embedder)
        results, below_threshold = retriever.retrieve("pump vibration", top_k=3)

        self.assertEqual(len(results), 0)
        self.assertTrue(below_threshold)

    def test_retrieve_mixed_threshold_filters_correctly(self):
        chunk_above = SQLDocumentChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            filename="pump_sop.pdf",
            source="user_upload",
            content="Pump details.",
            chunk_index=0,
            page_number=1,
            chunk_metadata={}
        )
        chunk_below = SQLDocumentChunk(
            chunk_id="chunk-2",
            document_id="doc-1",
            filename="pump_sop.pdf",
            source="user_upload",
            content="Unrelated text.",
            chunk_index=1,
            page_number=2,
            chunk_metadata={}
        )
        
        # pgvector query mock returns list of (chunk, score)
        self.db.query().order_by().limit().all.return_value = [
            (chunk_above, 0.85),
            (chunk_below, 0.45)
        ]

        retriever = KnowledgeBaseRetriever(self.db, self.embedder)
        results, below_threshold = retriever.retrieve("pump vibration", top_k=3)

        self.assertEqual(len(results), 1)
        self.assertFalse(below_threshold)
        self.assertEqual(results[0]["chunk_id"], "chunk-1")

    def test_retrieve_empty_query_rejected(self):
        retriever = KnowledgeBaseRetriever(self.db, self.embedder)
        with self.assertRaises(SearchQueryError):
            retriever.retrieve("")

    def test_retrieve_invalid_top_k_rejected(self):
        retriever = KnowledgeBaseRetriever(self.db, self.embedder)
        with self.assertRaises(SearchQueryError):
            retriever.retrieve("vibration", top_k=25)


class TestRAGAPIAndCORS(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.mock_db = MagicMock()
        # Register dependency override for database session
        from app.database import get_db
        app.dependency_overrides[get_db] = lambda: self.mock_db

    def tearDown(self):
        from app.database import get_db
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]

    def test_get_status_does_not_initialize_embedding_model(self):
        self.mock_db.query().distinct().count.return_value = 2
        self.mock_db.query().count.return_value = 10

        with patch("app.rag.embeddings.BGEM3EmbeddingProvider.initialize") as mock_init:
            response = self.client.get("/knowledge-base")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["documents_indexed"], 2)
            self.assertEqual(response.json()["chunks_indexed"], 10)
            mock_init.assert_not_called()

    @patch("sentence_transformers.SentenceTransformer", side_effect=OSError("Model not found"))
    def test_search_missing_bgem3_returns_503_and_cors(self, mock_transformer_cls):
        response = self.client.post(
            "/knowledge-base/search",
            json={"query": "pump vibration", "top_k": 3},
            headers={"Origin": "http://localhost:5173"}
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("not available locally", response.json()["detail"])
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5173")
        self.assertEqual(response.headers.get("access-control-allow-credentials"), "true")

    def test_get_status_missing_postgresql_returns_503_and_cors(self):
        # Setup mock db query to raise exception to simulate PostgreSQL offline
        self.mock_db.query.side_effect = Exception("Connection refused")

        response = self.client.get("/knowledge-base", headers={"Origin": "http://localhost:5173"})
        
        self.assertEqual(response.status_code, 503)
        self.assertIn("database connection failed", response.json()["detail"])
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5173")
        self.assertEqual(response.headers.get("access-control-allow-credentials"), "true")

    @patch("app.services.metadata_store.DocumentMetadataStore.get")
    @patch("app.services.storage.LocalDocumentStorage.get_extracted_document")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embeddings")
    def test_index_document_api_endpoint_succeeds(self, mock_get_embeddings, mock_get_extracted_document, mock_get_metadata):
        # 1. Mock Document Metadata Store
        mock_get_metadata.return_value = {
            "document_id": "test-doc-id",
            "filename": "sop.pdf",
            "source": "user_upload",
            "uploaded_at": "2026-08-26T12:00:00Z"
        }

        # 2. Mock Extracted Document
        mock_get_extracted_document.return_value = ExtractedDocument(
            document_id="test-doc-id",
            filename="sop.pdf",
            source="user_upload",
            content="Standard Operating Procedure text containing ≤ and °.",
            content_type="text",
            extraction_status="processed",
            metadata={"checksum_sha256": "fake-sha"},
            created_at="2026-08-26T12:00:00Z"
        )

        # 3. Mock Embeddings
        mock_get_embeddings.return_value = [[0.1] * 1024]
        
        # 4. Mock pgvector database operations (duplicate check empty)
        self.mock_db.query().filter().all.return_value = []

        # 5. Call API
        response = self.client.post(
            "/knowledge-base/index/test-doc-id",
            headers={"Origin": "http://localhost:5173"}
        )

        # 6. Verify status and response
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["document_id"], "test-doc-id")
        self.assertEqual(data["filename"], "sop.pdf")
        self.assertEqual(data["status"], "indexed")
        self.assertEqual(data["chunks_created"], 1)

        # Check CORS headers are present on successful 201 response
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:5173")
        self.assertEqual(response.headers.get("access-control-allow-credentials"), "true")


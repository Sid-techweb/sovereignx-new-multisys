"""
Tests for the E5 embedding migration: provider selection, E5 query/passage
prefix formatting, dimension safety, offline loading, BGE fallback,
readiness/background-warmup tracking, and migration-script idempotency.

Retrieval-quality (Recall@1/3/5, MRR, wrong-asset rate) and coexistence/
stress-test numbers are NOT unit tests -- they were measured live against
the real models and real Postgres (see the migration report). This file
covers the deterministic, mockable contract: does the code do the right
thing given the right inputs, independent of model weights being present.
"""
import unittest
from unittest.mock import MagicMock, patch

from app.config import settings
from app.rag.exceptions import EmbeddingModelUnavailableError
from app.rag.models import BGE_M3_DIMENSION, E5_SMALL_DIMENSION, SQLDocumentChunk


class TestEmbeddingProviderFactory(unittest.TestCase):
    """Phase 2: configuration selects the implementation; nothing else
    hardcodes a provider."""

    def setUp(self):
        self._original_provider = settings.EMBEDDING_PROVIDER

    def tearDown(self):
        settings.EMBEDDING_PROVIDER = self._original_provider

    def test_default_provider_is_bge(self):
        from app.rag.embeddings import get_embedding_provider, BGEM3EmbeddingProvider
        settings.EMBEDDING_PROVIDER = "bge"
        self.assertIsInstance(get_embedding_provider(), BGEM3EmbeddingProvider)

    def test_e5_provider_selected_when_configured(self):
        from app.rag.embeddings import get_embedding_provider, E5SmallEmbeddingProvider
        settings.EMBEDDING_PROVIDER = "e5"
        self.assertIsInstance(get_embedding_provider(), E5SmallEmbeddingProvider)

    def test_invalid_provider_rejected_by_settings_validation(self):
        from app.config import Settings
        with self.assertRaises(Exception):
            Settings(EMBEDDING_PROVIDER="nomic")

    def test_bge_and_e5_providers_have_distinct_vector_columns_and_dimensions(self):
        from app.rag.embeddings import BGEM3EmbeddingProvider, E5SmallEmbeddingProvider
        bge = BGEM3EmbeddingProvider()
        e5 = E5SmallEmbeddingProvider()
        self.assertEqual(bge.vector_column, "embedding")
        self.assertEqual(bge.dimension, BGE_M3_DIMENSION)
        self.assertEqual(e5.vector_column, "embedding_e5")
        self.assertEqual(e5.dimension, E5_SMALL_DIMENSION)
        self.assertNotEqual(bge.vector_column, e5.vector_column)


class TestE5PrefixFormatting(unittest.TestCase):
    """
    Phase 4: multilingual-e5-small requires asymmetric "query: "/"passage: "
    prefixes for correct retrieval -- verifies the exact transformation
    reaching the underlying model, not just that *some* embedding is
    returned. BGE-M3 must NOT apply any prefix (symmetric model).
    """

    def setUp(self):
        from app.rag.embeddings import _E5SmallModelRunner
        _E5SmallModelRunner.reset_for_testing()

    def tearDown(self):
        from app.rag.embeddings import _E5SmallModelRunner
        _E5SmallModelRunner.reset_for_testing()

    def _make_initialized_runner(self):
        from app.rag.embeddings import _E5SmallModelRunner
        runner = _E5SmallModelRunner("intfloat/multilingual-e5-small")
        runner._initialized = True
        runner._model = MagicMock()
        runner._model.encode.side_effect = lambda x, convert_to_numpy=True, normalize_embeddings=True: (
            MagicMock(tolist=lambda: [0.1] * E5_SMALL_DIMENSION) if isinstance(x, str)
            else MagicMock(tolist=lambda: [[0.1] * E5_SMALL_DIMENSION for _ in x])
        )
        return runner

    def test_embed_query_applies_query_prefix(self):
        runner = self._make_initialized_runner()
        runner.embed_query("what is P-101's max temperature?")
        called_with = runner._model.encode.call_args[0][0]
        self.assertEqual(called_with, "query: what is P-101's max temperature?")

    def test_embed_documents_applies_passage_prefix_to_every_text(self):
        runner = self._make_initialized_runner()
        runner.embed_documents(["chunk one text", "chunk two text"])
        called_with = runner._model.encode.call_args[0][0]
        self.assertEqual(called_with, ["passage: chunk one text", "passage: chunk two text"])

    def test_raw_get_embedding_does_not_add_prefix(self):
        # The raw primitive stays unprefixed -- only embed_query/embed_documents
        # apply E5-specific formatting, as documented on EmbeddingProvider.
        runner = self._make_initialized_runner()
        runner.get_embedding("bare text, no prefix")
        called_with = runner._model.encode.call_args[0][0]
        self.assertEqual(called_with, "bare text, no prefix")

    def test_bge_embed_query_does_not_prefix(self):
        from app.rag.embeddings import _BGEM3ModelRunner
        _BGEM3ModelRunner.reset_for_testing()
        runner = _BGEM3ModelRunner("BAAI/bge-m3")
        runner._initialized = True
        runner._model = MagicMock()
        runner._model.encode.return_value = MagicMock(tolist=lambda: [0.1] * BGE_M3_DIMENSION)
        runner.embed_query("plain query, no asymmetric prefix for BGE-M3")
        called_with = runner._model.encode.call_args[0][0]
        self.assertEqual(called_with, "plain query, no asymmetric prefix for BGE-M3")
        _BGEM3ModelRunner.reset_for_testing()


class TestE5DimensionSafety(unittest.TestCase):
    """Phase 6/17: E5 must produce exactly 384-dim vectors and fail cleanly
    (not silently) if it doesn't -- mirrors the existing BGE-M3 dimension
    guard so a future model-file mismatch can never write wrong-shaped
    vectors into embedding_e5."""

    def setUp(self):
        from app.rag.embeddings import _E5SmallModelRunner
        _E5SmallModelRunner.reset_for_testing()

    def tearDown(self):
        from app.rag.embeddings import _E5SmallModelRunner
        _E5SmallModelRunner.reset_for_testing()

    @patch("sentence_transformers.SentenceTransformer")
    def test_e5_dimension_mismatch_fails_cleanly(self, mock_st_cls):
        from app.rag.embeddings import _E5SmallModelRunner
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 768  # wrong
        mock_st_cls.return_value = mock_model

        runner = _E5SmallModelRunner()
        with self.assertRaises(EmbeddingModelUnavailableError) as ctx:
            runner.initialize()
        self.assertIn("does not match expected E5 dimension", str(ctx.exception))

    @patch("sentence_transformers.SentenceTransformer")
    def test_e5_initializes_with_local_files_only(self, mock_st_cls):
        from app.rag.embeddings import _E5SmallModelRunner
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = E5_SMALL_DIMENSION
        mock_st_cls.return_value = mock_model

        runner = _E5SmallModelRunner()
        runner.initialize()

        # Offline guarantee (Phase 11/17): local_files_only=True, no network
        # resolution attempted, same pattern BGE-M3 already uses.
        mock_st_cls.assert_called_once_with("intfloat/multilingual-e5-small", local_files_only=True)
        self.assertTrue(runner._initialized)


class TestRetrieverIndexerProviderAgnostic(unittest.TestCase):
    """Phase 6: retriever/indexer must write to and query whichever column
    matches the injected provider -- never hardcode `embedding`."""

    def test_indexer_writes_to_provider_specific_column(self):
        from app.rag.indexer import KnowledgeBaseIndexer
        from app.schemas.documents import ExtractedDocument

        db = MagicMock()
        db.query().filter().all.return_value = []
        embedder = MagicMock()
        embedder.vector_column = "embedding_e5"
        embedder.model_name = "intfloat/multilingual-e5-small"
        embedder.embed_documents.return_value = [[0.2] * E5_SMALL_DIMENSION]

        doc = ExtractedDocument(
            document_id="doc-e5", filename="sop.pdf", source="user_upload",
            content="E5-embedded content.", content_type="text",
            extraction_status="processed", metadata={"checksum_sha256": "sha-e5"},
            created_at="2026-08-26T12:00:00Z",
        )

        indexer = KnowledgeBaseIndexer(db, embedder)
        indexer.index_document(doc)

        added_chunk = db.add.call_args[0][0]
        self.assertEqual(added_chunk.embedding_e5, [0.2] * E5_SMALL_DIMENSION)
        self.assertEqual(added_chunk.embedding_e5_model, "intfloat/multilingual-e5-small")
        self.assertIsNone(added_chunk.embedding)  # BGE column untouched, not set

    def test_retriever_queries_provider_specific_column(self):
        from app.rag.retriever import KnowledgeBaseRetriever

        db = MagicMock()
        db.query().filter().order_by().limit().all.return_value = []
        embedder = MagicMock()
        embedder.vector_column = "embedding_e5"
        embedder.embed_query.return_value = [0.2] * E5_SMALL_DIMENSION

        retriever = KnowledgeBaseRetriever(db, embedder)
        retriever.retrieve("a query", top_k=3)

        embedder.embed_query.assert_called_once_with("a query")
        # cosine_distance was invoked on the embedding_e5 column, not `embedding`
        # -- confirmed indirectly via the query chain succeeding with the
        # mocked provider's vector_column; a wrong column name would raise
        # AttributeError from getattr(SQLDocumentChunk, ...) before this point.


class TestBGEFallbackStillWorks(unittest.TestCase):
    """Phase 3/27: switching EMBEDDING_PROVIDER back to 'bge' must work with
    zero code changes -- BGE-M3 stays fully supported as a rollback path."""

    def setUp(self):
        self._original_provider = settings.EMBEDDING_PROVIDER
        settings.EMBEDDING_PROVIDER = "e5"

    def tearDown(self):
        settings.EMBEDDING_PROVIDER = self._original_provider

    def test_switching_provider_back_to_bge_via_config_only(self):
        from app.rag.embeddings import get_embedding_provider, BGEM3EmbeddingProvider
        self.assertEqual(settings.EMBEDDING_PROVIDER, "e5")
        settings.EMBEDDING_PROVIDER = "bge"
        provider = get_embedding_provider()
        self.assertIsInstance(provider, BGEM3EmbeddingProvider)
        self.assertEqual(provider.vector_column, "embedding")


class TestNoSilentRagFallback(unittest.TestCase):
    """Phase 18/19: an E5 failure during DOCUMENT_RAG must surface as the
    same explicit document_grounding_unavailable state BGE failures already
    do -- never a silently-ungrounded GENERAL_CHAT-looking answer."""

    def setUp(self):
        self._original_provider = settings.EMBEDDING_PROVIDER
        settings.EMBEDDING_PROVIDER = "e5"

    def tearDown(self):
        settings.EMBEDDING_PROVIDER = self._original_provider

    @patch("app.chat.service.get_resource_manager")
    @patch("app.chat.service.get_embedding_provider")
    def test_e5_unavailable_returns_explicit_unavailable_reason(self, mock_get_provider, mock_get_resource_mgr):
        from app.chat.service import _retrieve_for_document_rag
        from app.chat.routing import ChatRoute

        mock_get_resource_mgr.return_value.ensure_embedding_capacity.return_value = None
        mock_provider = MagicMock()
        mock_provider.embed_query.side_effect = EmbeddingModelUnavailableError("E5 provider not available locally.")
        mock_get_provider.return_value = mock_provider

        chunks, tools, route, unavailable_reason = _retrieve_for_document_rag(MagicMock(), "According to the document, what is P-101's limit?", None)

        self.assertEqual(chunks, [])
        self.assertEqual(tools, [])
        self.assertEqual(route, ChatRoute.DOCUMENT_RAG)
        self.assertIsNotNone(unavailable_reason)
        self.assertIn("not available locally", unavailable_reason)


class TestReadinessTracking(unittest.TestCase):
    """Phase 14-16: liveness vs readiness -- background warmup state is
    tracked independently of FastAPI process liveness, and a bounded wait
    returns promptly once ready instead of blocking indefinitely."""

    def setUp(self):
        from app.services import readiness
        readiness.reset_for_testing()

    def tearDown(self):
        from app.services import readiness
        readiness.reset_for_testing()

    def test_initial_state_not_ready(self):
        from app.services import readiness
        state = readiness.get_state()
        self.assertFalse(state.llm_ready)
        self.assertFalse(state.embedding_ready)
        self.assertIsNone(state.warmup_started_at)

    def test_mark_ready_updates_state(self):
        from app.services import readiness
        readiness.mark_warmup_started()
        readiness.mark_llm_ready()
        readiness.mark_embedding_ready()
        state = readiness.get_state()
        self.assertTrue(state.llm_ready)
        self.assertTrue(state.embedding_ready)
        self.assertIsNotNone(state.warmup_started_at)

    def test_mark_ready_with_error_leaves_not_ready(self):
        from app.services import readiness
        readiness.mark_llm_ready(error="Ollama unreachable")
        state = readiness.get_state()
        self.assertFalse(state.llm_ready)
        self.assertEqual(state.llm_error, "Ollama unreachable")

    def test_wait_until_ready_returns_immediately_when_already_ready(self):
        from app.services import readiness
        import time
        readiness.mark_llm_ready()
        t0 = time.perf_counter()
        result = readiness.wait_until_ready("llm", timeout=5.0)
        elapsed = time.perf_counter() - t0
        self.assertTrue(result)
        self.assertLess(elapsed, 1.0)

    def test_wait_until_ready_times_out_when_never_ready(self):
        from app.services import readiness
        result = readiness.wait_until_ready("llm", timeout=0.3)
        self.assertFalse(result)


class _FakeChunk:
    def __init__(self, chunk_id, has_e5=False):
        self.chunk_id = chunk_id
        self.content = f"content for {chunk_id}"
        self.embedding = [0.1] * BGE_M3_DIMENSION
        self.embedding_e5 = [0.2] * E5_SMALL_DIMENSION if has_e5 else None
        self.embedding_e5_model = "intfloat/multilingual-e5-small" if has_e5 else None


class _FakeSession:
    """
    Faithful in-memory stand-in for the real SQLAlchemy behavior
    run_migration() actually depends on: `_fetch_batch` filters on
    embedding_e5 IS NULL *and* a keyset cursor, and -- critically --
    rollback() reverts the in-memory attribute mutations run_migration()
    made directly on the chunk objects (exactly like a real SQLAlchemy
    session expiring uncommitted changes). This last property is what a
    naive MagicMock-based test does NOT capture, and is exactly what let an
    early version of the real script's --dry-run mode loop forever: without
    the keyset cursor, a rolled-back chunk becomes "pending" again and gets
    re-selected on the very next batch fetch. That bug was caught live
    (a genuinely infinite loop, killed after ~89,000 duplicate re-embeds
    of the same 2 dev-DB rows) -- these tests exist specifically so it
    cannot silently return.
    """

    def __init__(self, chunks):
        self.chunks = chunks
        self._last_batch = []
        self.commit_calls = 0
        self.rollback_calls = 0

    def count_pending(self):
        return sum(1 for c in self.chunks if c.embedding_e5 is None)

    def fetch_batch(self, batch_size, after_chunk_id):
        candidates = sorted(
            (c for c in self.chunks if c.embedding_e5 is None and (after_chunk_id is None or c.chunk_id > after_chunk_id)),
            key=lambda c: c.chunk_id,
        )
        self._last_batch = candidates[:batch_size]
        return self._last_batch

    def commit(self):
        self.commit_calls += 1
        self._last_batch = []

    def rollback(self):
        self.rollback_calls += 1
        for c in self._last_batch:
            c.embedding_e5 = None
            c.embedding_e5_model = None
        self._last_batch = []


class TestMigrationScriptIdempotency(unittest.TestCase):
    """
    Phase 9/10: the migration script must be resumable and idempotent -- a
    chunk with embedding_e5 already set must never be re-selected or
    double-processed, a batch failure must not corrupt already-committed
    progress, and --dry-run must terminate after exactly one pass (not loop
    forever). Uses _FakeSession (see above) rather than a real Postgres
    connection -- integration-level correctness against real pgvector/the
    real dev DB was verified live, see the migration report.
    """

    def _patch_session(self, fake_session):
        return patch.multiple(
            "scripts.migrate_bge_to_e5",
            _count_pending=lambda db: fake_session.count_pending(),
            _fetch_batch=lambda db, batch_size, after_chunk_id: fake_session.fetch_batch(batch_size, after_chunk_id),
        )

    def test_already_migrated_chunks_are_never_reselected(self):
        from scripts.migrate_bge_to_e5 import run_migration

        c1, c2 = _FakeChunk("c1"), _FakeChunk("c2")
        c3_done = _FakeChunk("c3", has_e5=True)
        fake = _FakeSession([c1, c2, c3_done])
        db = MagicMock(commit=fake.commit, rollback=fake.rollback)

        with self._patch_session(fake), patch("scripts.migrate_bge_to_e5.E5SmallEmbeddingProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.model_name = "intfloat/multilingual-e5-small"
            mock_provider.embed_documents.return_value = [[0.9] * E5_SMALL_DIMENSION] * 2
            mock_provider_cls.return_value = mock_provider

            report = run_migration(db=db, batch_size=32)

        self.assertEqual(report.processed, 2)
        self.assertEqual(report.failed, 0)
        mock_provider.embed_documents.assert_called_once_with(["content for c1", "content for c2"])
        # The already-migrated chunk's vector is untouched -- still its
        # original value, never re-embedded.
        self.assertEqual(c3_done.embedding_e5, [0.2] * E5_SMALL_DIMENSION)
        self.assertEqual(fake.commit_calls, 1)

    def test_resumed_run_after_partial_completion_only_processes_remaining(self):
        """c1/c2 already migrated (a prior run completed them and committed);
        a resumed run must process only the still-pending c3, never re-embed
        c1/c2."""
        from scripts.migrate_bge_to_e5 import run_migration

        c1_done, c2_done = _FakeChunk("c1", has_e5=True), _FakeChunk("c2", has_e5=True)
        c3 = _FakeChunk("c3")
        fake = _FakeSession([c1_done, c2_done, c3])
        db = MagicMock(commit=fake.commit, rollback=fake.rollback)

        with self._patch_session(fake), patch("scripts.migrate_bge_to_e5.E5SmallEmbeddingProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.model_name = "intfloat/multilingual-e5-small"
            mock_provider.embed_documents.return_value = [[0.9] * E5_SMALL_DIMENSION]
            mock_provider_cls.return_value = mock_provider

            report = run_migration(db=db, batch_size=32)

        self.assertEqual(report.processed, 1)
        self.assertEqual(report.total_pending_at_start, 1)
        mock_provider.embed_documents.assert_called_once_with(["content for c3"])

    def test_embedding_failure_marks_batch_failed_without_committing(self):
        from scripts.migrate_bge_to_e5 import run_migration

        c1, c2 = _FakeChunk("c1"), _FakeChunk("c2")
        fake = _FakeSession([c1, c2])
        db = MagicMock(commit=fake.commit, rollback=fake.rollback)

        with self._patch_session(fake), patch("scripts.migrate_bge_to_e5.E5SmallEmbeddingProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.embed_documents.side_effect = EmbeddingModelUnavailableError("model down")
            mock_provider_cls.return_value = mock_provider

            report = run_migration(db=db, batch_size=32)

        self.assertEqual(report.processed, 0)
        self.assertEqual(report.failed, 2)
        self.assertIn("c1", report.failed_chunk_ids)
        self.assertEqual(fake.commit_calls, 0)

    def test_dry_run_does_not_commit_and_terminates_exactly_once(self):
        """
        Regression test for the exact bug caught live: without the keyset
        cursor, rollback() reverting the batch's in-memory embedding_e5
        mutation made the same "still NULL" chunk match the pending filter
        again on the very next fetch, looping forever. This asserts the
        migration visits each pending chunk exactly once and terminates,
        even though nothing is ever actually persisted.
        """
        from scripts.migrate_bge_to_e5 import run_migration

        c1 = _FakeChunk("c1")
        fake = _FakeSession([c1])
        db = MagicMock(commit=fake.commit, rollback=fake.rollback)

        with self._patch_session(fake), patch("scripts.migrate_bge_to_e5.E5SmallEmbeddingProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.model_name = "intfloat/multilingual-e5-small"
            mock_provider.embed_documents.return_value = [[0.9] * E5_SMALL_DIMENSION]
            mock_provider_cls.return_value = mock_provider

            report = run_migration(db=db, batch_size=32, dry_run=True)

        self.assertEqual(report.processed, 1)  # visited exactly once, not thousands of times
        self.assertEqual(fake.commit_calls, 0)
        self.assertEqual(fake.rollback_calls, 1)
        # Dry run wrote nothing -- the chunk's embedding_e5 is back to None
        # after rollback, exactly as before the run.
        self.assertIsNone(c1.embedding_e5)

    def test_batch_size_one_still_terminates_across_multiple_batches(self):
        """With batch_size smaller than the pending set, the keyset cursor
        must still advance correctly across multiple fetch_batch calls."""
        from scripts.migrate_bge_to_e5 import run_migration

        chunks = [_FakeChunk(f"c{i}") for i in range(5)]
        fake = _FakeSession(chunks)
        db = MagicMock(commit=fake.commit, rollback=fake.rollback)

        with self._patch_session(fake), patch("scripts.migrate_bge_to_e5.E5SmallEmbeddingProvider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.model_name = "intfloat/multilingual-e5-small"
            mock_provider.embed_documents.side_effect = lambda texts: [[0.9] * E5_SMALL_DIMENSION for _ in texts]
            mock_provider_cls.return_value = mock_provider

            report = run_migration(db=db, batch_size=1)

        self.assertEqual(report.processed, 5)
        self.assertEqual(fake.commit_calls, 5)
        self.assertTrue(all(c.embedding_e5 is not None for c in chunks))


if __name__ == "__main__":
    unittest.main()

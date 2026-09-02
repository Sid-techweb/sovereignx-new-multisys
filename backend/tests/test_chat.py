import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.config import settings
from app.database import get_db
from app.chat.models import ChatConversation, ChatMessage
from app.gateway import get_gateway
from app.gateway.exceptions import OllamaUnavailableError


class TestChatEndpoints(unittest.TestCase):
    """
    Endpoint-level tests for the new general-purpose + RAG-optional chat
    path (POST /chat/conversations/{id}/messages). Uses a real in-memory
    SQLite session (only the two new chat tables) so conversation memory is
    genuinely exercised end-to-end, and a mocked ModelGateway so no local
    model / Ollama server is required to run the suite.
    """

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        ChatConversation.__table__.create(self.engine)
        ChatMessage.__table__.create(self.engine)
        TestingSessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self._session = TestingSessionLocal()

        def override_get_db():
            yield self._session

        self.mock_gateway = MagicMock()
        self.mock_gateway.chat_completion = AsyncMock(return_value="mock answer")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_gateway] = lambda: self.mock_gateway
        self.client = TestClient(app, headers={"X-API-Key": settings.API_KEY})

        # ModelResourceManager isn't a FastAPI dependency (chat/service.py
        # calls it directly), so it can't go through dependency_overrides --
        # patch it here instead so tests never make a real network call to
        # Ollama's /api/ps or spawn a real BGE worker. Its own behavior is
        # covered separately in test_model_resource_manager.py.
        self.mock_resource_manager = MagicMock()
        self.mock_resource_manager.ensure_embedding_available.return_value = None
        self.mock_resource_manager.ensure_llm_capacity.return_value = {"resource_wait_ms": 0.0}
        self._resource_manager_patcher = patch(
            "app.chat.service.get_resource_manager", return_value=self.mock_resource_manager
        )
        self._resource_manager_patcher.start()

    def tearDown(self):
        self._resource_manager_patcher.stop()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_gateway, None)
        self._session.close()
        self.engine.dispose()

    def _new_conversation(self) -> str:
        res = self.client.post("/chat/conversations")
        self.assertEqual(res.status_code, 201)
        return res.json()["conversation_id"]

    # --- General chat: no RAG dependency required ---

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    def test_general_chat_answers_without_documents(self, mock_retrieve):
        """A plain general question must be answered directly by the local model,
        without ever touching the RAG retriever, and without any document
        existing in the knowledge base."""
        self.mock_gateway.chat_completion.return_value = (
            "Machine learning is a field of AI where systems learn from data."
        )
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "What is machine learning?"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["route"], "GENERAL_CHAT")
        self.assertIn("Machine learning", data["answer"])
        self.assertEqual(data["retrieved_chunks"], [])
        mock_retrieve.assert_not_called()

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    def test_no_external_search_dependency_for_general_chat(self, mock_retrieve):
        """General chat must never invoke the RAG/knowledge-base retriever
        (the only local 'search' surface in this codebase) -- there is no
        web/cloud search integration to invoke in the first place."""
        conversation_id = self._new_conversation()
        self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "Compare REST and gRPC."},
        )
        mock_retrieve.assert_not_called()
        self.mock_gateway.chat_completion.assert_called_once()

    # --- Follow-up conversational memory ---

    def test_followup_question_includes_prior_turn_context(self):
        conversation_id = self._new_conversation()
        self.mock_gateway.chat_completion.return_value = "Kafka is a distributed event streaming platform."

        res1 = self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "Explain Kafka."},
        )
        self.assertEqual(res1.status_code, 200)

        self.mock_gateway.chat_completion.return_value = "Unlike Kafka, RabbitMQ is a traditional message broker."
        res2 = self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "How is it different from RabbitMQ?"},
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["route"], "GENERAL_CHAT")

        # Inspect the messages actually sent to the model on the second call --
        # the first turn's exchange must be present so "it" resolves to Kafka.
        second_call_messages = self.mock_gateway.chat_completion.call_args_list[1][0][0]
        joined = " ".join(m["content"] for m in second_call_messages)
        self.assertIn("Explain Kafka.", joined)
        self.assertIn("Kafka is a distributed event streaming platform.", joined)
        self.assertIn("How is it different from RabbitMQ?", joined)

    # --- Explicit document-scoped query routes to RAG ---

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embedding")
    def test_explicit_document_query_routes_to_rag(self, mock_get_embedding, mock_retrieve):
        mock_retrieve.return_value = (
            [{
                "chunk_id": "c1", "document_id": "d1", "filename": "manual.pdf",
                "source": "user_upload", "content": "Maximum operating temperature is 85 C.",
                "score": 0.92, "metadata": {}
            }],
            False,
        )
        self.mock_gateway.chat_completion.return_value = "The maximum operating temperature is 85 C [manual.pdf]."
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "According to the uploaded document, what is the maximum temperature?"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["route"], "DOCUMENT_RAG")
        self.assertEqual(len(data["retrieved_chunks"]), 1)
        self.assertEqual(data["retrieved_chunks"][0]["filename"], "manual.pdf")
        mock_retrieve.assert_called_once()

    # --- RAG regression: known document + known fact still grounded ---

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embedding")
    def test_rag_regression_grounded_answer_with_citation(self, mock_get_embedding, mock_retrieve):
        mock_retrieve.return_value = (
            [{
                "chunk_id": "c1", "document_id": "d1", "filename": "pump_SOP.pdf",
                "source": "user_upload", "content": "Bearing housing temperature limit is 80 C.",
                "score": 0.91, "metadata": {}
            }],
            False,
        )
        self.mock_gateway.chat_completion.return_value = "The SOP bearing temperature limit is 80 C [pump_SOP.pdf]."
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "Summarize the uploaded report on bearing temperature limits."},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["route"], "DOCUMENT_RAG")
        self.assertIn("80 C", data["answer"])
        self.assertIn("[pump_SOP.pdf]", data["answer"])

    # --- Document-scoped query with no relevant chunks must not hard-block ---

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embedding")
    def test_document_scoped_query_with_no_chunks_still_answers(self, mock_get_embedding, mock_retrieve):
        """Unlike the legacy /agents/investigate endpoint (which hard-fails
        with 400 when the knowledge base is empty), the new chat path must
        still return a usable answer even when RAG finds nothing relevant."""
        mock_retrieve.return_value = ([], False)
        self.mock_gateway.chat_completion.return_value = (
            "The provided documents do not cover this, but in general..."
        )
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "According to the report, what is the maximum temperature?"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["route"], "DOCUMENT_RAG")
        self.assertEqual(data["retrieved_chunks"], [])

    # --- Provider unavailable: clean, model-specific error ---

    def test_model_provider_unavailable_returns_clean_error(self):
        self.mock_gateway.chat_completion.side_effect = OllamaUnavailableError("Could not connect to Ollama server")
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "What is Python?"},
        )

        self.assertEqual(res.status_code, 503)
        self.assertIn("Local language model is currently unavailable", res.json()["detail"])

    # --- Explicit document requests must NEVER silently degrade to GENERAL_CHAT ---
    #
    # This was a real bug caught by a live benchmark: after Qwen loaded and
    # became resident, a second consecutive DOCUMENT_RAG turn found BGE
    # unable to start, and the OLD behavior silently answered as
    # GENERAL_CHAT -- an ungrounded answer presented as if grounding had
    # succeeded. The fix: an explicit document request that cannot be
    # grounded must return route=DOCUMENT_RAG with rag_unavailable_reason
    # set and a fixed refusal answer, never a normal-looking answer, and
    # must NOT call the model gateway at all.

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embedding")
    def test_explicit_document_request_never_silently_becomes_general_chat(self, mock_get_embedding, mock_retrieve):
        from app.rag.exceptions import DatabaseConnectionError
        mock_retrieve.side_effect = DatabaseConnectionError("pgvector unreachable")
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "According to the document, what is the limit?"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["route"], "DOCUMENT_RAG")
        self.assertIsNone(data["rag_degraded_reason"])
        self.assertIsNotNone(data["rag_unavailable_reason"])
        self.assertIn("document-grounded", data["answer"])
        # Internal diagnostics must not leak to the user-facing answer.
        self.assertNotIn("pgvector unreachable", data["answer"])
        # The gateway must never have been called for this turn.
        self.mock_gateway.chat_completion.assert_not_called()

    def test_document_grounding_unavailable_reports_reason_without_leaking_internals(self):
        from app.rag.exceptions import EmbeddingModelUnavailableError
        self.mock_resource_manager.ensure_embedding_capacity.side_effect = EmbeddingModelUnavailableError(
            "Local embedding model is temporarily unavailable: insufficient system memory headroom "
            "(915MB free, 2048MB safety margin required)."
        )
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "According to the uploaded document, what is P-101's max temperature?"},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["route"], "DOCUMENT_RAG")
        self.assertIsNotNone(data["rag_unavailable_reason"])
        self.assertNotIn("915MB", data["answer"])
        self.assertNotIn("commit", data["answer"].lower())

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embedding")
    def test_five_consecutive_document_requests_all_stay_grounded(self, mock_get_embedding, mock_retrieve):
        """Regression test for the exact failure pattern the benchmark found:
        repeated document-scoped turns in the same conversation must all
        stay DOCUMENT_RAG, never silently drift to GENERAL_CHAT."""
        mock_retrieve.return_value = (
            [{
                "chunk_id": "c1", "document_id": "d1", "filename": "pump_sop.pdf",
                "source": "user_upload", "content": "Pump P-101 max temp 85 C.",
                "score": 0.9, "metadata": {}
            }],
            False,
        )
        self.mock_gateway.chat_completion.return_value = "85 C [pump_sop.pdf]."
        conversation_id = self._new_conversation()

        for i in range(5):
            res = self.client.post(
                f"/chat/conversations/{conversation_id}/messages",
                json={"message": f"According to the document, question {i}?"},
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["route"], "DOCUMENT_RAG", f"turn {i} did not stay DOCUMENT_RAG")
            self.assertIsNone(data["rag_unavailable_reason"])

    # --- Deterministic arithmetic routing ---

    def test_arithmetic_question_uses_verified_tool_result(self):
        self.mock_gateway.chat_completion.return_value = "10384 x 827 = 8587568."
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "What is 10384 times 827? Explain the steps."},
        )

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["route"], "EXISTING_TOOL_FLOW")
        self.assertEqual(len(data["tool_executions"]), 1)
        self.assertEqual(data["tool_executions"][0]["outputs"]["computed"], 8587568.0)
        # The gateway IS still called (to explain the verified result), but
        # the verified number must have been computed deterministically,
        # not asserted from the (mocked) LLM's own output.
        self.mock_gateway.chat_completion.assert_called_once()
        sent_messages = self.mock_gateway.chat_completion.call_args[0][0]
        joined = " ".join(m["content"] for m in sent_messages)
        self.assertIn("8587568", joined)

    # --- Conversation history endpoint ---

    def test_conversation_message_history_is_retrievable(self):
        conversation_id = self._new_conversation()
        self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "Hello there."},
        )
        res = self.client.get(f"/chat/conversations/{conversation_id}/messages")
        self.assertEqual(res.status_code, 200)
        roles = [m["role"] for m in res.json()]
        self.assertEqual(roles, ["user", "assistant"])


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.config import settings
from app.database import get_db
from app.chat.models import ChatConversation, ChatMessage
from app.gateway import get_gateway, StreamChunk
from app.gateway.exceptions import OllamaUnavailableError


def _fake_stream(chunks):
    """Builds a stand-in for gateway.stream_chat_completion: an async
    generator function yielding pre-scripted StreamChunks (or raising, if a
    chunk entry is an Exception instance)."""
    async def _stream(messages, options=None):
        for item in chunks:
            if isinstance(item, Exception):
                raise item
            yield item
    return _stream


def _read_ndjson(response):
    events = []
    for line in response.text.strip().split("\n"):
        if line.strip():
            events.append(json.loads(line))
    return events


class TestChatStreamingEndpoint(unittest.TestCase):
    """Priority 2 (service/API layer): the streaming endpoint delivers
    incremental token events, persists exactly one final assistant message,
    and handles failures before/after partial generation cleanly."""

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
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_gateway] = lambda: self.mock_gateway
        self.client = TestClient(app, headers={"X-API-Key": settings.API_KEY})

        # See test_chat.py's setUp for why this is patched directly rather
        # than via dependency_overrides.
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

    def _row_count(self, model, conversation_id):
        return self._session.query(model).filter(model.conversation_id == conversation_id).count()

    # --- Streaming general chat delivers incremental chunks ---

    def test_streaming_general_chat_delivers_incremental_chunks(self):
        self.mock_gateway.stream_chat_completion = _fake_stream([
            StreamChunk(content="Machine ", done=False),
            StreamChunk(content="learning ", done=False),
            StreamChunk(content="is fun.", done=False),
            StreamChunk(content="", done=True, metadata={
                "total_duration_ms": 50.0, "load_duration_ms": 1.0,
                "prompt_eval_duration_ms": 5.0, "eval_duration_ms": 40.0,
                "prompt_eval_count": 10, "eval_count": 3,
            }),
        ])
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages/stream",
            json={"message": "What is machine learning?"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "application/x-ndjson")

        events = _read_ndjson(res)
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "start")
        self.assertEqual(types[-1], "done")
        token_events = [e for e in events if e["type"] == "token"]
        self.assertEqual(len(token_events), 3)
        self.assertEqual("".join(e["content"] for e in token_events), "Machine learning is fun.")

        done_event = events[-1]
        self.assertEqual(done_event["route"], "GENERAL_CHAT")
        self.assertEqual(done_event["answer"], "Machine learning is fun.")
        self.assertIsNotNone(done_event["timings_ms"]["ttft_ms"])
        self.assertIn("total_ms", done_event["timings_ms"])
        self.assertEqual(done_event["ollama_metadata"]["eval_count"], 3)

    # --- Exactly one final assistant message persisted, not one per chunk ---

    def test_exactly_one_assistant_message_persisted(self):
        self.mock_gateway.stream_chat_completion = _fake_stream([
            StreamChunk(content="a", done=False),
            StreamChunk(content="b", done=False),
            StreamChunk(content="c", done=False),
            StreamChunk(content="d", done=False),
            StreamChunk(content="e", done=False),
            StreamChunk(content="", done=True, metadata={"eval_count": 5}),
        ])
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages/stream",
            json={"message": "spell it out"},
        )
        self.assertEqual(res.status_code, 200)

        user_count = self._session.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation_id, ChatMessage.role == "user"
        ).count()
        assistant_count = self._session.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation_id, ChatMessage.role == "assistant"
        ).count()
        self.assertEqual(user_count, 1)
        self.assertEqual(assistant_count, 1)

        assistant_row = self._session.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation_id, ChatMessage.role == "assistant"
        ).first()
        self.assertEqual(assistant_row.content, "abcde")

    # --- Ollama failure before first token ---

    def test_ollama_failure_before_first_token_yields_error_event_no_assistant_row(self):
        self.mock_gateway.stream_chat_completion = _fake_stream([
            OllamaUnavailableError("Could not connect to Ollama server"),
        ])
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages/stream",
            json={"message": "hello"},
        )
        self.assertEqual(res.status_code, 200)  # stream already started with 200
        events = _read_ndjson(res)
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["category"], "model_unavailable")
        self.assertIn("unavailable", events[-1]["message"].lower())

        # user message still persisted (sent before generation started);
        # no assistant message, since zero tokens were produced.
        self.assertEqual(self._row_count(ChatMessage, conversation_id), 1)
        user_row = self._session.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation_id
        ).first()
        self.assertEqual(user_row.role, "user")

    # --- Ollama failure after partial generation ---

    def test_ollama_failure_after_partial_generation_persists_partial_as_one_message(self):
        self.mock_gateway.stream_chat_completion = _fake_stream([
            StreamChunk(content="The answer is ", done=False),
            OllamaUnavailableError("connection dropped mid-stream"),
        ])
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages/stream",
            json={"message": "explain something long"},
        )
        self.assertEqual(res.status_code, 200)
        events = _read_ndjson(res)
        token_events = [e for e in events if e["type"] == "token"]
        self.assertEqual(len(token_events), 1)
        error_event = events[-1]
        self.assertEqual(error_event["type"], "error")
        self.assertEqual(error_event["partial_content"], "The answer is ")

        # exactly one assistant row, containing the partial text -- not lost, not duplicated
        assistant_rows = self._session.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation_id, ChatMessage.role == "assistant"
        ).all()
        self.assertEqual(len(assistant_rows), 1)
        self.assertEqual(assistant_rows[0].content, "The answer is ")

    # --- DOCUMENT_RAG routing still works over streaming ---

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embedding")
    def test_streaming_document_scoped_query_routes_to_rag(self, mock_get_embedding, mock_retrieve):
        mock_retrieve.return_value = (
            [{
                "chunk_id": "c1", "document_id": "d1", "filename": "manual.pdf",
                "source": "user_upload", "content": "Maximum operating temperature is 85 C.",
                "score": 0.9, "metadata": {}
            }],
            False,
        )
        self.mock_gateway.stream_chat_completion = _fake_stream([
            StreamChunk(content="The max temperature is 85 C [manual.pdf].", done=False),
            StreamChunk(content="", done=True, metadata={"eval_count": 8}),
        ])
        conversation_id = self._new_conversation()

        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages/stream",
            json={"message": "According to the uploaded document, what is the maximum temperature?"},
        )
        self.assertEqual(res.status_code, 200)
        events = _read_ndjson(res)
        self.assertEqual(events[0]["type"], "start")
        self.assertEqual(events[0]["route"], "DOCUMENT_RAG")
        self.assertEqual(len(events[0]["retrieved_chunks"]), 1)
        self.assertEqual(events[-1]["route"], "DOCUMENT_RAG")
        mock_retrieve.assert_called_once()

    # --- No external network dependency for streamed general chat ---

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    def test_streaming_general_chat_never_touches_retriever(self, mock_retrieve):
        self.mock_gateway.stream_chat_completion = _fake_stream([
            StreamChunk(content="42", done=False),
            StreamChunk(content="", done=True, metadata={"eval_count": 1}),
        ])
        conversation_id = self._new_conversation()
        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages/stream",
            json={"message": "What is 6 times 7?"},
        )
        self.assertEqual(res.status_code, 200)
        mock_retrieve.assert_not_called()

    # --- Conversation history still works over streaming ---

    def test_streaming_followup_includes_prior_turn_context(self):
        self.mock_gateway.stream_chat_completion = _fake_stream([
            StreamChunk(content="Kafka is a streaming platform.", done=False),
            StreamChunk(content="", done=True, metadata={"eval_count": 5}),
        ])
        conversation_id = self._new_conversation()
        res1 = self.client.post(
            f"/chat/conversations/{conversation_id}/messages/stream",
            json={"message": "Explain Kafka."},
        )
        self.assertEqual(res1.status_code, 200)

        captured_messages = {}

        def _stream_capture(messages, options=None):
            captured_messages["value"] = messages
            async def _gen():
                yield StreamChunk(content="It differs in X.", done=False)
                yield StreamChunk(content="", done=True, metadata={"eval_count": 3})
            return _gen()
        self.mock_gateway.stream_chat_completion = _stream_capture

        res2 = self.client.post(
            f"/chat/conversations/{conversation_id}/messages/stream",
            json={"message": "How is it different from RabbitMQ?"},
        )
        self.assertEqual(res2.status_code, 200)

        joined = " ".join(m["content"] for m in captured_messages["value"])
        self.assertIn("Explain Kafka.", joined)
        self.assertIn("Kafka is a streaming platform.", joined)


class TestNonStreamingUnaffected(unittest.TestCase):
    """Confirms the existing non-streaming gateway/endpoint were not broken
    by adding the streaming path."""

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
        from unittest.mock import AsyncMock
        self.mock_gateway.chat_completion = AsyncMock(return_value="A non-streamed answer.")
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_gateway] = lambda: self.mock_gateway
        self.client = TestClient(app, headers={"X-API-Key": settings.API_KEY})

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

    def test_non_streaming_endpoint_still_works(self):
        res = self.client.post("/chat/conversations")
        conversation_id = res.json()["conversation_id"]
        res = self.client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"message": "What is Python?"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["route"], "GENERAL_CHAT")
        self.assertEqual(data["answer"], "A non-streamed answer.")
        self.mock_gateway.stream_chat_completion.assert_not_called()


if __name__ == "__main__":
    unittest.main()

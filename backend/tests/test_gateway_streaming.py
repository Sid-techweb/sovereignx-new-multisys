import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from app.gateway.ollama import OllamaGateway
from app.gateway.exceptions import OllamaUnavailableError, ProviderExecutionError


class _FakeOllamaStreamResponse:
    """Minimal stand-in for the httpx.Response yielded by `client.stream(...)`."""
    def __init__(self, lines, status_code=200):
        self._lines = lines
        self.status_code = status_code

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return b'{"error":"boom"}'


class _FakeStreamCtx:
    """Minimal stand-in for the async context manager httpx.AsyncClient.stream() returns."""
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _ndjson(*objs):
    return [json.dumps(o) for o in objs]


class TestOllamaKeepAlive(unittest.TestCase):
    """Priority 1: keep_alive must be threaded through to Ollama's request payload,
    driven by centralized config rather than hardcoded anywhere."""

    @patch("httpx.AsyncClient.post")
    def test_chat_completion_includes_configured_keep_alive(self, mock_post):
        import asyncio
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "hi"}}

        async def fake_post(*args, **kwargs):
            return mock_response
        mock_post.side_effect = fake_post

        gateway = OllamaGateway(base_url="http://localhost:11434", model_name="qwen2.5:7b", keep_alive="30m")
        asyncio.run(gateway.chat_completion([{"role": "user", "content": "hi"}]))

        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["keep_alive"], "30m")

    @patch("httpx.AsyncClient.post")
    def test_chat_completion_omits_keep_alive_when_not_configured(self, mock_post):
        import asyncio
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "hi"}}

        async def fake_post(*args, **kwargs):
            return mock_response
        mock_post.side_effect = fake_post

        gateway = OllamaGateway(base_url="http://localhost:11434", model_name="qwen2.5:7b")
        asyncio.run(gateway.chat_completion([{"role": "user", "content": "hi"}]))

        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertNotIn("keep_alive", sent_payload)

    @patch("httpx.AsyncClient.stream")
    def test_stream_chat_completion_includes_configured_keep_alive(self, mock_stream):
        import asyncio
        lines = _ndjson(
            {"message": {"content": "hi"}, "done": False},
            {"message": {"content": ""}, "done": True, "total_duration": 1, "load_duration": 1,
             "prompt_eval_duration": 1, "eval_duration": 1, "prompt_eval_count": 1, "eval_count": 1},
        )
        mock_stream.return_value = _FakeStreamCtx(_FakeOllamaStreamResponse(lines))

        gateway = OllamaGateway(base_url="http://localhost:11434", model_name="qwen2.5:7b", keep_alive="30m")

        async def collect():
            return [c async for c in gateway.stream_chat_completion([{"role": "user", "content": "hi"}])]
        asyncio.run(collect())

        sent_payload = mock_stream.call_args.kwargs["json"]
        self.assertEqual(sent_payload["keep_alive"], "30m")
        self.assertTrue(sent_payload["stream"])


class TestOllamaThink(unittest.TestCase):
    """
    Model-aware `think` generation option (Settings.OLLAMA_THINK), driven by
    config rather than hardcoded per model in the gateway. Applied uniformly
    to both chat_completion and stream_chat_completion, so GENERAL_CHAT,
    DOCUMENT_RAG, and EXISTING_TOOL_FLOW (which all share these two gateway
    methods) get consistent generation behavior automatically.
    """

    @patch("httpx.AsyncClient.post")
    def test_chat_completion_includes_configured_think_false(self, mock_post):
        import asyncio
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "hi"}}

        async def fake_post(*args, **kwargs):
            return mock_response
        mock_post.side_effect = fake_post

        gateway = OllamaGateway(base_url="http://localhost:11434", model_name="qwen3.5:4b", think=False)
        asyncio.run(gateway.chat_completion([{"role": "user", "content": "hi"}]))

        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent_payload["think"], False)

    @patch("httpx.AsyncClient.post")
    def test_chat_completion_omits_think_when_not_configured(self, mock_post):
        import asyncio
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "hi"}}

        async def fake_post(*args, **kwargs):
            return mock_response
        mock_post.side_effect = fake_post

        # think=None (the default when unset) -- must be safe for any model,
        # including one with no thinking capability at all (e.g. qwen2.5:7b).
        gateway = OllamaGateway(base_url="http://localhost:11434", model_name="qwen2.5:7b")
        asyncio.run(gateway.chat_completion([{"role": "user", "content": "hi"}]))

        sent_payload = mock_post.call_args.kwargs["json"]
        self.assertNotIn("think", sent_payload)

    @patch("httpx.AsyncClient.stream")
    def test_stream_chat_completion_includes_configured_think_false(self, mock_stream):
        import asyncio
        lines = _ndjson(
            {"message": {"content": "hi"}, "done": False},
            {"message": {"content": ""}, "done": True, "total_duration": 1, "load_duration": 1,
             "prompt_eval_duration": 1, "eval_duration": 1, "prompt_eval_count": 1, "eval_count": 1},
        )
        mock_stream.return_value = _FakeStreamCtx(_FakeOllamaStreamResponse(lines))

        gateway = OllamaGateway(base_url="http://localhost:11434", model_name="qwen3.5:4b", think=False)

        async def collect():
            return [c async for c in gateway.stream_chat_completion([{"role": "user", "content": "hi"}])]
        asyncio.run(collect())

        sent_payload = mock_stream.call_args.kwargs["json"]
        self.assertEqual(sent_payload["think"], False)


class TestOllamaStreamChatCompletion(unittest.TestCase):
    """Priority 2 (gateway layer): stream_chat_completion parses Ollama's
    NDJSON stream into incremental chunks and preserves the final timing
    metadata, without replacing the existing non-streaming chat_completion."""

    @patch("httpx.AsyncClient.stream")
    def test_yields_incremental_chunks_then_final_metadata(self, mock_stream):
        import asyncio
        lines = _ndjson(
            {"message": {"content": "Hello"}, "done": False},
            {"message": {"content": " world"}, "done": False},
            {"message": {"content": ""}, "done": True, "total_duration": 5_000_000, "load_duration": 1_000_000,
             "prompt_eval_duration": 500_000, "eval_duration": 3_000_000, "prompt_eval_count": 10, "eval_count": 2},
        )
        mock_stream.return_value = _FakeStreamCtx(_FakeOllamaStreamResponse(lines))

        gateway = OllamaGateway(base_url="http://localhost:11434", model_name="qwen2.5:7b")

        async def collect():
            return [c async for c in gateway.stream_chat_completion([{"role": "user", "content": "hi"}])]
        chunks = asyncio.run(collect())

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].content, "Hello")
        self.assertFalse(chunks[0].done)
        self.assertEqual(chunks[1].content, " world")
        self.assertFalse(chunks[1].done)
        self.assertTrue(chunks[2].done)
        self.assertEqual(chunks[2].metadata["eval_count"], 2)
        self.assertEqual(chunks[2].metadata["load_duration_ms"], 1.0)
        self.assertEqual(chunks[2].metadata["total_duration_ms"], 5.0)

        full_text = "".join(c.content for c in chunks)
        self.assertEqual(full_text, "Hello world")

    @patch("httpx.AsyncClient.stream")
    def test_ollama_http_error_before_any_token_raises(self, mock_stream):
        import asyncio
        mock_stream.return_value = _FakeStreamCtx(_FakeOllamaStreamResponse([], status_code=500))

        gateway = OllamaGateway(base_url="http://localhost:11434", model_name="qwen2.5:7b")

        async def collect():
            return [c async for c in gateway.stream_chat_completion([{"role": "user", "content": "hi"}])]

        with self.assertRaises(ProviderExecutionError):
            asyncio.run(collect())

    @patch("httpx.AsyncClient.stream")
    def test_connection_error_raises_ollama_unavailable(self, mock_stream):
        import asyncio
        import httpx

        def raise_connect_error(*args, **kwargs):
            raise httpx.ConnectError("connection refused")
        mock_stream.side_effect = raise_connect_error

        gateway = OllamaGateway(base_url="http://localhost:11434", model_name="qwen2.5:7b")

        async def collect():
            return [c async for c in gateway.stream_chat_completion([{"role": "user", "content": "hi"}])]

        with self.assertRaises(OllamaUnavailableError):
            asyncio.run(collect())

    @patch("httpx.AsyncClient.stream")
    def test_error_mid_stream_after_partial_tokens_raises(self, mock_stream):
        """Simulates Ollama's llama-server crashing after some tokens were
        already emitted -- the error must surface after the partial chunks,
        not silently swallow them."""
        import asyncio
        lines = _ndjson(
            {"message": {"content": "Hello"}, "done": False},
            {"error": "llama-server process has terminated"},
        )
        mock_stream.return_value = _FakeStreamCtx(_FakeOllamaStreamResponse(lines))

        gateway = OllamaGateway(base_url="http://localhost:11434", model_name="qwen2.5:7b")
        received = []

        async def collect():
            async for c in gateway.stream_chat_completion([{"role": "user", "content": "hi"}]):
                received.append(c)

        with self.assertRaises(ProviderExecutionError):
            asyncio.run(collect())

        # The partial token must have been delivered before the error surfaced.
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].content, "Hello")


if __name__ == "__main__":
    unittest.main()

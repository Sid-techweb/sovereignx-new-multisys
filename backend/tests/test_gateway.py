import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.gateway import get_gateway, ModelGateway, MockGateway, OllamaGateway
from app.gateway.exceptions import UnsupportedProviderError, OllamaUnavailableError

class TestGatewayArchitecture(unittest.TestCase):
    def setUp(self):
        # Ensure we run tests using the FastAPI test client
        self.client = TestClient(app, headers={"X-API-Key": settings.API_KEY})

    def test_mock_provider_startup(self):
        """Test 1 — Mock provider starts successfully"""
        with patch.object(settings, "MODEL_PROVIDER", "mock"):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok", "service": "sovereignx-backend"})

    def test_phase_1_behavior(self):
        """Test 2 — Phase 1 behavior: returns static analysis response on compressor prompt"""
        prompt = (
            "Compressor C-118 discharge pressure = 14.2 bar.\n"
            "Design limit = 12.5 bar.\n"
            "Noise level abnormal, unit vibrating."
        )
        
        with patch.object(settings, "MODEL_PROVIDER", "mock"):
            response = self.client.post("/models/chat", json={"prompt": prompt})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            # Verify the response is exactly the Phase 1 static mock output
            self.assertEqual(data["finding"], "Bearing housing temperature exceeds the specified SOP threshold.")
            self.assertEqual(data["sop_reference"], "Maintenance SOP Section 4.2")
            self.assertEqual(data["confidence"], 0.87)
            self.assertEqual(data["recommended_action"], "Inspect lubrication and bearing clearance.")

    def test_provider_abstraction(self):
        """Test 3 — Provider abstraction: verify the app uses the ModelGateway abstraction"""
        with patch.object(settings, "MODEL_PROVIDER", "mock"):
            gateway = get_gateway()
            # Verify the returned gateway is an instance of the abstract class
            self.assertTrue(isinstance(gateway, ModelGateway))
            self.assertTrue(isinstance(gateway, MockGateway))
            self.assertTrue(hasattr(gateway, "analyze"))

    def test_factory_threads_ollama_think_from_settings(self):
        """OLLAMA_THINK is config-driven, not hardcoded per model in the
        gateway -- the factory must pass the currently configured value
        straight through, whatever MODEL_NAME is set to."""
        with patch.object(settings, "MODEL_PROVIDER", "ollama"), \
             patch.object(settings, "OLLAMA_THINK", False):
            gateway = get_gateway()
            self.assertIsInstance(gateway, OllamaGateway)
            self.assertEqual(gateway.think, False)

        with patch.object(settings, "MODEL_PROVIDER", "ollama"), \
             patch.object(settings, "OLLAMA_THINK", None):
            gateway = get_gateway()
            self.assertIsNone(gateway.think)

    def test_invalid_provider(self):
        """Test 4 — Invalid provider: clean configuration/provider error"""
        with patch.object(settings, "MODEL_PROVIDER", "invalid"):
            # Check that get_gateway directly raises UnsupportedProviderError
            with self.assertRaises(UnsupportedProviderError):
                get_gateway()
            
            # Check that calling models/chat endpoint yields a clean HTTP 500 error details
            response = self.client.post("/models/chat", json={"prompt": "test prompt"})
            self.assertEqual(response.status_code, 500)
            data = response.json()
            self.assertIn("detail", data)
            self.assertEqual(data["detail"], "Unsupported model provider: invalid")

    def test_ollama_unavailable(self):
        """Test 5 — Ollama unavailable: produces clear controlled error (503 Service Unavailable)"""
        with patch.object(settings, "MODEL_PROVIDER", "ollama"):
            with patch.object(settings, "OLLAMA_BASE_URL", "http://localhost:9999"):
                response = self.client.post("/models/chat", json={"prompt": "test prompt"})
                self.assertEqual(response.status_code, 503)
                data = response.json()
                self.assertIn("detail", data)
                self.assertIn("Could not connect to Ollama server", data["detail"])

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embedding")
    @patch("app.gateway.ollama.OllamaGateway.generate")
    def test_grounded_query_success(self, mock_generate, mock_get_embedding, mock_retrieve):
        """Test 6 — Grounded query with retrieved evidence returns success response with correct prompt construction"""
        mock_retrieve.return_value = (
            [
                {
                    "chunk_id": "chunk-123",
                    "document_id": "doc-456",
                    "filename": "pump_data.csv",
                    "source": "user_upload",
                    "content": "Pump P-204 experienced abnormal discharge pressure.",
                    "score": 0.95,
                    "metadata": {"page_number": 2, "chunk_index": 5}
                }
            ],
            False
        )
        mock_generate.return_value = "According to [Source: pump_data.csv | document_id=doc-456 | chunk_id=chunk-123 | page=2], Pump P-204 experienced abnormal discharge pressure."

        with patch.object(settings, "MODEL_PROVIDER", "ollama"):
            response = self.client.post("/models/grounded-query", json={"query": "P-204 issue"})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["query"], "P-204 issue")
            self.assertIn("[Source: pump_data.csv | document_id=doc-456 | chunk_id=chunk-123 | page=2]", data["answer"])
            self.assertEqual(len(data["retrieved_chunks"]), 1)
            self.assertEqual(data["retrieved_chunks"][0]["filename"], "pump_data.csv")

            # Check that generate was called with a prompt containing query and evidence
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args[1]
            self.assertIn("P-204 issue", call_args["prompt"])
            self.assertIn("Pump P-204 experienced abnormal discharge pressure", call_args["prompt"])
            self.assertIn("Source: pump_data.csv | document_id=doc-456 | chunk_id=chunk-123 | page=2 | chunk_index=5", call_args["prompt"])
            self.assertIn("Every single sentence you write must contain exactly one fact, immediately followed by the citation", call_args["system_prompt"])

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embedding")
    @patch("app.gateway.ollama.OllamaGateway.generate")
    def test_grounded_query_empty_evidence(self, mock_generate, mock_get_embedding, mock_retrieve):
        """Test 7 — Grounded query with empty evidence handles empty list safely without fabrication"""
        mock_retrieve.return_value = ([], False)
        mock_generate.return_value = "The provided evidence is insufficient to answer the question."

        with patch.object(settings, "MODEL_PROVIDER", "ollama"):
            response = self.client.post("/models/grounded-query", json={"query": "P-204 issue"})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["answer"], "The provided evidence is insufficient to answer the question.")
            self.assertEqual(len(data["retrieved_chunks"]), 0)

            # Check that generate was called with warning of no evidence
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args[1]
            self.assertIn("[No evidence found in the knowledge base]", call_args["prompt"])

    @patch("httpx.AsyncClient.post")
    def test_ollama_gateway_analyze_success(self, mock_post):
        """Test 8 — OllamaGateway.analyze parses JSON response correctly"""
        import asyncio
        from app.schemas.analysis import AnalysisRequest
        
        mock_response = unittest.mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": '{"finding": "Test finding", "sop_reference": "SOP Section 1.2", "confidence": 0.95, "recommended_action": "Do test"}'
        }
        
        async def mock_post_coro(*args, **kwargs):
            return mock_response
        mock_post.side_effect = mock_post_coro

        gateway = OllamaGateway(base_url="http://localhost:11434", model_name="qwen2.5:7b")
        req = AnalysisRequest(input_text="Compressor issue")
        res = asyncio.run(gateway.analyze(req))

        self.assertEqual(res.finding, "Test finding")
        self.assertEqual(res.sop_reference, "SOP Section 1.2")
        self.assertEqual(res.confidence, 0.95)
        self.assertEqual(res.recommended_action, "Do test")


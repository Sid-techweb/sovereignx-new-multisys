import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.agents import IntakeAgent, RAGAgent, AnalysisAgent, ReportAgent
from app.gateway import ModelGateway
from app.gateway.exceptions import OllamaUnavailableError

class TestAgentWiring(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_intake_agent_availability(self):
        """Test IntakeAgent verify_evidence_availability behaves correctly"""
        agent = IntakeAgent()
        
        # When DB has count > 0, return True
        mock_db = MagicMock()
        mock_db.query().count.return_value = 5
        self.assertTrue(agent.verify_evidence_availability(mock_db))

        # When DB has count == 0, return False
        mock_db.query().count.return_value = 0
        self.assertFalse(agent.verify_evidence_availability(mock_db))

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embedding")
    def test_rag_agent_retrieve(self, mock_get_embedding, mock_retrieve):
        """Test RAGAgent correctly calls KnowledgeBaseRetriever"""
        mock_db = MagicMock()
        mock_retrieve.return_value = ([{"filename": "test.pdf", "score": 0.85}], False)
        
        agent = RAGAgent(mock_db)
        results = agent.retrieve_evidence("P-204 issue")
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["filename"], "test.pdf")
        mock_retrieve.assert_called_once_with("P-204 issue", top_k=5)

    @patch("app.gateway.ollama.OllamaGateway.generate")
    def test_analysis_agent_and_tool_wiring(self, mock_generate):
        """Test AnalysisAgent coordinates generation and dynamically triggers tool calls"""
        mock_generate.return_value = (
            "The bearing housing temperature was 91 C. "
            "The SOP limit is 80 C. "
            "The vibration was 5.8 mm/s. "
            "The SOP vibration limit is 4.0 mm/s."
        )
        
        mock_chunks = [
            {
                "chunk_id": "c1",
                "document_id": "d1",
                "filename": "pump_P204_sensor_data.csv",
                "content": "temperature_c: 91\nvibration_mm_s: 5.8",
                "score": 0.9
            },
            {
                "chunk_id": "c2",
                "document_id": "d2",
                "filename": "pump_P204_SOP.pdf",
                "content": "bearing temperature limit is 80 C\nvibration limit is 4.0 mm/s",
                "score": 0.8
            }
        ]
        
        mock_gateway = MagicMock(spec=ModelGateway)
        mock_gateway.generate = mock_generate
        mock_gateway.model_name = "qwen2.5:7b"
        
        agent = AnalysisAgent(mock_gateway)
        
        # Execute analysis with context_id
        import asyncio
        result = asyncio.run(agent.analyze("P-204", mock_chunks, context_id="ctx-999"))
        
        self.assertEqual(result["answer"], mock_generate.return_value)
        self.assertEqual(len(result["tool_executions"]), 2)
        
        # Verify first tool execution (temperature comparison)
        t_exec = result["tool_executions"][0]
        self.assertEqual(t_exec["tool_name"], "compare_reading_against_sop_limit")
        self.assertEqual(t_exec["status"], "success")
        self.assertEqual(t_exec["context_id"], "ctx-999")
        self.assertTrue(t_exec["outputs"]["is_exceeded"])
        self.assertIn("Exceedance detected", t_exec["outputs"]["summary"])

        # Verify second tool execution (vibration comparison)
        v_exec = result["tool_executions"][1]
        self.assertEqual(v_exec["tool_name"], "compare_reading_against_sop_limit")
        self.assertEqual(v_exec["status"], "success")
        self.assertEqual(v_exec["context_id"], "ctx-999")
        self.assertTrue(v_exec["outputs"]["is_exceeded"])
        self.assertIn("Exceedance detected", v_exec["outputs"]["summary"])

    def test_report_agent_confidence_calculation(self):
        """Test ReportAgent calculates confidence cleanly as the average score of chunks"""
        agent = ReportAgent()
        
        mock_chunks = [
            {"score": 0.8},
            {"score": 0.9},
            {"score": 0.7}
        ]
        
        report = agent.format_report(
            query="test query",
            answer="grounded answer",
            retrieved_chunks=mock_chunks,
            tool_executions=[],
            model_used="qwen2.5:7b",
            latency_ms=150.0
        )
        
        self.assertEqual(report["confidence"], 0.8) # average of 0.8, 0.9, 0.7
        self.assertEqual(report["query"], "test query")
        self.assertEqual(report["answer"], "grounded answer")
        self.assertEqual(report["metadata"]["model_used"], "qwen2.5:7b")

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embedding")
    @patch("app.gateway.ollama.OllamaGateway.generate")
    @patch("app.agents.IntakeAgent.verify_evidence_availability")
    def test_investigate_endpoint_success(self, mock_intake, mock_generate, mock_get_embedding, mock_retrieve):
        """Test POST /agents/investigate endpoint returns structured response successfully"""
        mock_intake.return_value = True
        mock_retrieve.return_value = (
            [
                {
                    "chunk_id": "c1",
                    "document_id": "d1",
                    "filename": "pump_P204_sensor_data.csv",
                    "content": "temperature_c: 91\nvibration_mm_s: 5.8",
                    "score": 0.9
                },
                {
                    "chunk_id": "c2",
                    "document_id": "d2",
                    "filename": "pump_P204_SOP.pdf",
                    "content": "bearing temperature limit is 80 C\nvibration limit is 4.0 mm/s",
                    "score": 0.8
                }
            ],
            False
        )
        mock_generate.return_value = "Answer context."
        
        with patch.object(settings, "MODEL_PROVIDER", "ollama"):
            response = self.client.post(
                "/agents/investigate",
                json={"query": "What happened to Pump P-204?", "context_id": "test-context-123"}
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            self.assertEqual(data["query"], "What happened to Pump P-204?")
            self.assertEqual(data["answer"], "Answer context.")
            self.assertEqual(data["confidence"], 0.85) # (0.9 + 0.8) / 2
            self.assertEqual(len(data["tool_executions"]), 2)
            self.assertEqual(data["tool_executions"][0]["context_id"], "test-context-123")
            self.assertEqual(data["metadata"]["model_used"], "qwen2.5:7b")

    @patch("app.rag.retriever.KnowledgeBaseRetriever.retrieve")
    @patch("app.rag.embeddings.BGEM3EmbeddingProvider.get_embedding")
    @patch("app.gateway.ollama.OllamaGateway.generate")
    @patch("app.agents.IntakeAgent.verify_evidence_availability")
    def test_investigate_endpoint_insufficient_evidence(self, mock_intake, mock_generate, mock_get_embedding, mock_retrieve):
        """Test POST /agents/investigate returns warning when RAG returns empty chunks for unrelated query"""
        mock_intake.return_value = True
        mock_retrieve.return_value = ([], False)
        mock_generate.return_value = "The provided evidence is insufficient to answer the question."
        
        with patch.object(settings, "MODEL_PROVIDER", "ollama"):
            response = self.client.post(
                "/agents/investigate",
                json={"query": "What is the maintenance history of Compressor C-900?", "context_id": "test-context-900"}
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            
            self.assertEqual(data["query"], "What is the maintenance history of Compressor C-900?")
            self.assertEqual(data["answer"], "The provided evidence is insufficient to answer the question.")
            self.assertEqual(data["confidence"], 0.0)
            self.assertEqual(len(data["tool_executions"]), 0)

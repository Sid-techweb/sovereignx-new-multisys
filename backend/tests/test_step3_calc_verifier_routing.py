import sys
from pathlib import Path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

import unittest
import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock
from app.agents.agents import AnalysisAgent, is_calculation_check_query
from app.tools.calculation_verifier import extract_calculation_with_llm_async

class TestCalcVerifierRouting(unittest.TestCase):
    def test_routing_detection_cases(self):
        # Test A
        self.assertFalse(is_calculation_check_query("Temperature = 91 C. Is this within the SOP limit?"))
        
        # Test B
        self.assertFalse(is_calculation_check_query("Is the current vibration reading within the permitted SOP limit?"))
        
        # Test C
        self.assertTrue(is_calculation_check_query("Calculate the pump efficiency using these values."))
        
        # Test D
        self.assertTrue(is_calculation_check_query("Verify this engineering calculation."))
        
        # Additional engineering calculation test cases
        self.assertTrue(is_calculation_check_query("Verify calculation: P = F / A where F = 500 N and A = 2.5 m2."))
        self.assertTrue(is_calculation_check_query("Check formula Q = K * sqrt(dp) with K = 12.0"))
        
        # Part A Adversarial Test Cases
        # 1. Negative-delta reading phrasing with standalone minus sign
        self.assertFalse(is_calculation_check_query("Temperature drop = -5 C from baseline of 85 C. Is this within the SOP limit?"))
        self.assertFalse(is_calculation_check_query("Vibration change = -0.5 mm/s compared to last reading."))
        
        # 2. Genuine calculation query with bare-number-looking RHS
        self.assertTrue(is_calculation_check_query("Calculate pump efficiency where power = 500 W."))
        self.assertTrue(is_calculation_check_query("Verify calculation: efficiency = 200"))
        
        # 3. Real-world inspection phrasing variant
        self.assertFalse(is_calculation_check_query("During inspection, bearing housing temperature was recorded at 91 C, exceeding the SOP-permitted maximum of 80 C. Please confirm."))

    def test_rag_only_query(self):
        # Test E: RAG-only question should remain RAG-only
        self.assertFalse(is_calculation_check_query("What is the procedure for starting Pump P-204?"))

    def test_coroutine_awaiting_fix_intact(self):
        # Test H: Confirm inspect.iscoroutine check from earlier session is intact
        source = inspect.getsource(extract_calculation_with_llm_async)
        self.assertIn("inspect.iscoroutine", source)

class TestAnalysisAgentWorkflow(unittest.IsolatedAsyncioTestCase):
    async def test_sop_temperature_exceeds_reproduction(self):
        # Test G: Original bug reproduction test case (91°C vs 80°C SOP limit)
        mock_gateway = AsyncMock()
        mock_gateway.generate.return_value = "The temperature reading of 91 C exceeds the SOP limit of 80 C [Source: pump_P204_SOP.pdf | chunk_id=c1]."
        
        agent = AnalysisAgent(gateway=mock_gateway)
        
        query = "Temperature = 91 C. Is this within the SOP limit?"
        retrieved_chunks = [{
            "document_id": "doc-123",
            "chunk_id": "c1",
            "filename": "pump_P204_SOP.pdf",
            "content": "Pump P-204 SOP: Maximum permitted temperature = 80 C.",
            "score": 0.88
        }]
        
        result = await agent.analyze(query=query, retrieved_chunks=retrieved_chunks)
        
        # Verify routing did NOT go to verify_engineering_calculation
        tool_execs = result.get("tool_executions", [])
        self.assertGreater(len(tool_execs), 0)
        
        exec_entry = tool_execs[0]
        self.assertEqual(exec_entry["tool_name"], "compare_reading_against_sop_limit")
        self.assertEqual(exec_entry["status"], "success")
        
        outputs = exec_entry.get("outputs", {})
        self.assertTrue(outputs.get("is_exceeded"))
        self.assertIn("91.0 C", outputs.get("summary", ""))
        self.assertIn("80.0 C", outputs.get("summary", ""))

    async def test_engineering_calculation_execution(self):
        # Verify verify_engineering_calculation still works for genuine calculation requests
        mock_gateway = AsyncMock()
        mock_gateway.generate.return_value = '{"formula": "F / A", "variables": {"F": 500, "A": 2.5}, "claimed_answer": 200, "extraction_confidence": "high"}'
        
        agent = AnalysisAgent(gateway=mock_gateway)
        query = "Verify calculation: P = F / A where F = 500 N and A = 2.5 m2. Claimed answer is 200 Pa."
        
        result = await agent.analyze(query=query, retrieved_chunks=[])
        tool_execs = result.get("tool_executions", [])
        self.assertEqual(len(tool_execs), 1)
        self.assertEqual(tool_execs[0]["tool_name"], "verify_engineering_calculation")
        self.assertIn("MATCH", result["answer"])

if __name__ == "__main__":
    unittest.main()

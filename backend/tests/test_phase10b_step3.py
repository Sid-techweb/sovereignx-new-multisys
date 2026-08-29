import pytest
import asyncio
from app.agents.agents import AnalysisAgent, is_calculation_check_query
from app.gateway.mock import MockGateway
from app.tools.calculation_verifier import (
    evaluate_expression,
    extract_and_verify_calculation_async,
    SecurityError
)

def test_detection_logic_classification():
    # Calculation check queries
    assert is_calculation_check_query("Verify calculation: P = F / A where F = 500 and A = 2.5") is True
    assert is_calculation_check_query("Check formula Q = K * sqrt(dp) with K = 12.0") is True
    assert is_calculation_check_query("Verify equation x = 5 + 10") is True

    # Standard operational queries (MUST NOT be misclassified)
    assert is_calculation_check_query("What happened to Pump P-204?") is False
    assert is_calculation_check_query("Summarise the P-204 anomaly against SOP and tell me whether it needs a shutdown") is False
    assert is_calculation_check_query("List all active cases in the refinery") is False

@pytest.mark.asyncio
async def test_exception_handling_zero_division():
    res = await extract_and_verify_calculation_async("x = 10 divided by 0", override_extracted={"formula": "x / 0", "variables": {"x": 10}, "extraction_confidence": "high"})
    assert res["status"] == "NEEDS_REVIEW"
    assert "calculation evaluation error" in res["summary"].lower()

@pytest.mark.asyncio
async def test_exception_handling_security_error():
    res = await extract_and_verify_calculation_async("x = 10 running __import__('os')", override_extracted={"formula": "__import__('os')", "variables": {"x": 10}, "extraction_confidence": "high"})
    assert res["status"] == "NEEDS_REVIEW"

@pytest.mark.asyncio
async def test_exception_handling_malformed_value_error():
    res = await extract_and_verify_calculation_async("x = 10 malformed 10 + * 5", override_extracted={"formula": "10 + * 5", "variables": {"x": 10}, "extraction_confidence": "high"})
    assert res["status"] == "NEEDS_REVIEW"

@pytest.mark.asyncio
async def test_exception_handling_undefined_variable():
    res = await extract_and_verify_calculation_async("a = 5 plus b", override_extracted={"formula": "a + b", "variables": {"a": 5}, "extraction_confidence": "high"})
    assert res["status"] == "NEEDS_REVIEW"

@pytest.mark.asyncio
async def test_analysis_agent_calculation_routing():
    gateway = MockGateway()
    agent = AnalysisAgent(gateway)

    query = "Verify calculation: P = F / A where F = 500 N and A = 2.5 m2. Claimed answer is 200 Pa."
    res = await agent.analyze(query, retrieved_chunks=[])

    assert "Engineering Calculation Verification" in res["answer"]
    assert len(res["tool_executions"]) == 1
    assert res["tool_executions"][0]["tool_name"] == "verify_engineering_calculation"

@pytest.mark.asyncio
async def test_p204_query_regression():
    gateway = MockGateway()
    agent = AnalysisAgent(gateway)

    query = "What happened to Pump P-204?"
    mock_chunks = [{
        "chunk_id": "chunk-123",
        "content": "Pump P-204 recorded temperature_c: 92.0 at 12:00 UTC. Bearing housing temperature limit: 80.0 C.",
        "score": 0.95
    }]
    res = await agent.analyze(query, retrieved_chunks=mock_chunks)

    # Confirm normal RAG response path
    assert "Engineering Calculation Verification" not in res["answer"]
    assert "Pump P-204" in res["answer"]

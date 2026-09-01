import math
import json
import pytest
from app.gateway.base import ModelGateway, StreamChunk
from app.tools.calculation_verifier import (
    evaluate_expression,
    verify_calculation,
    verify_extracted_data_against_source,
    extract_and_verify_calculation,
    extract_and_verify_calculation_async,
    parse_calculation_from_text,
    SecurityError
)

class MockCalculationGateway(ModelGateway):
    """Mock LLM gateway for exercising calculation extraction prompts in tests."""
    def __init__(self, mock_json_response: dict):
        self.mock_json_response = mock_json_response

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        return json.dumps(self.mock_json_response)

    async def analyze(self, request):
        pass

    async def chat_completion(self, messages, options=None) -> str:
        return json.dumps(self.mock_json_response)

    async def stream_chat_completion(self, messages, options=None):
        text = json.dumps(self.mock_json_response)
        yield StreamChunk(content=text, done=False)
        yield StreamChunk(content="", done=True, metadata={})


def test_basic_arithmetic():
    res = evaluate_expression("a + b * c", {"a": 10, "b": 5, "c": 2})
    assert res == 20.0

def test_parentheses_and_division():
    res = evaluate_expression("(a + b) / c", {"a": 10, "b": 5, "c": 3})
    assert res == 5.0

def test_power_operator_caret_and_double_star():
    res1 = evaluate_expression("x ^ 2", {"x": 4})
    res2 = evaluate_expression("x ** 3", {"x": 2})
    assert res1 == 16.0
    assert res2 == 8.0

def test_unary_operators():
    res = evaluate_expression("-x + (+y)", {"x": 5, "y": 12})
    assert res == 7.0

def test_whitelisted_function_sqrt():
    res = evaluate_expression("sqrt(val)", {"val": 144})
    assert res == 12.0

def test_whitelisted_function_log():
    res = evaluate_expression("log(x)", {"x": math.e})
    assert pytest.approx(res, 1e-6) == 1.0

def test_whitelisted_function_trig_and_abs():
    res = evaluate_expression("abs(-10) + sin(0) + cos(0)", {})
    assert res == 11.0

def test_sop_pressure_drop_formula():
    sop_expr = "K * density * (v ^ 2) / 2"
    variables = {"K": 0.5, "density": 1000.0, "v": 2.0}
    res = evaluate_expression(sop_expr, variables)
    assert res == 1000.0

def test_rejection_import_attempt():
    with pytest.raises((SecurityError, ValueError)):
        evaluate_expression("__import__('os').system('dir')", {})

def test_rejection_attribute_access():
    with pytest.raises((SecurityError, ValueError)):
        evaluate_expression("x.__class__.__name__", {"x": 10})

def test_rejection_non_whitelisted_function():
    with pytest.raises((SecurityError, ValueError)):
        evaluate_expression("open('file.txt')", {})
    with pytest.raises((SecurityError, ValueError)):
        evaluate_expression("eval('2+2')", {})

def test_rejection_subscripting():
    with pytest.raises((SecurityError, ValueError)):
        evaluate_expression("x[0]", {"x": [1, 2, 3]})

def test_rejection_missing_variable():
    with pytest.raises(ValueError) as exc:
        evaluate_expression("a + b", {"a": 5})
    assert "Undefined variable 'b'" in str(exc.value)

def test_zero_division_error():
    with pytest.raises(ZeroDivisionError):
        evaluate_expression("x / 0", {"x": 10})

def test_malformed_expression():
    with pytest.raises(ValueError):
        evaluate_expression("10 + * 5", {})

def test_verify_calculation_match_and_mismatch():
    match_res = verify_calculation("P1 * V1", {"P1": 2.0, "V1": 5.0}, claimed_answer=10.0)
    assert match_res["is_match"] is True
    assert match_res["status"] == "MATCH"

    mismatch_res = verify_calculation("P1 * V1", {"P1": 2.0, "V1": 5.0}, claimed_answer=12.5)
    assert mismatch_res["is_match"] is False
    assert mismatch_res["status"] == "MISMATCH"
    assert mismatch_res["delta"] == 2.5

# =====================================================================
# STEP 2 — 5 SAMPLE INPUT TESTS (TESTING LLM EXTRACTION & GATE DIRECTLY)
# =====================================================================

def test_step2_sample1_clean_unambiguous_pressure():
    input_text = "Verify pressure calculation: P = F / A where F = 500 N and A = 2.5 m2. Claimed answer is 200 Pa."
    res = extract_and_verify_calculation(input_text)
    
    assert res["gate_passed"] is True
    assert res["status"] == "MATCH"
    assert res["computed"] == 200.0
    assert res["claimed"] == 200.0
    assert res["delta"] == 0.0

def test_step2_sample2_clean_unambiguous_flow_sqrt():
    input_text = "Check flow rate formula Q = K * sqrt(dp) with K = 12.0 and dp = 16.0. Claimed result = 48.0."
    res = extract_and_verify_calculation(input_text)
    
    assert res["gate_passed"] is True
    assert res["status"] == "MATCH"
    assert res["computed"] == 48.0
    assert res["claimed"] == 48.0

def test_step2_sample3_out_of_scope_calculus():
    input_text = "Calculate integral of f(x) = x^2 from 0 to 10."
    res = extract_and_verify_calculation(input_text)
    
    assert res["gate_passed"] is False
    assert res["status"] == "NEEDS_REVIEW"

def test_step2_sample4_ambiguous_incomplete():
    input_text = "The pressure in pump P-204 is too high, please calculate if it exceeds standard limits."
    res = extract_and_verify_calculation(input_text)
    
    assert res["gate_passed"] is False
    assert res["status"] == "NEEDS_REVIEW"

@pytest.mark.asyncio
async def test_step2_async_llm_gateway_raw_text_extraction():
    # Test LLM extraction gateway with raw text input (NO override_extracted!)
    raw_input_text = "The engineer calculated force F = 500 N across area A = 2.5 m2. Formula P = F / A. Claimed pressure is 200 Pa."
    
    mock_llm_payload = {
        "formula": "F / A",
        "variables": {"F": 500.0, "A": 2.5},
        "claimed_answer": 200.0,
        "extraction_confidence": "high"
    }
    mock_gateway = MockCalculationGateway(mock_llm_payload)

    res = await extract_and_verify_calculation_async(raw_input_text, gateway=mock_gateway)
    
    assert res["gate_passed"] is True
    assert res["status"] == "MATCH"
    assert res["computed"] == 200.0
    assert res["claimed"] == 200.0

@pytest.mark.asyncio
async def test_step2_async_llm_adversarial_mismatched_value_gate():
    # Test LLM extraction gateway returning a hallucinated value (A = 9.9) not in raw source text
    raw_source_text = "Flow velocity v = 4.0 m/s and pipe area A = 0.5 m2. Formula Q = v * A. Claimed flow rate is 2.0 m3/s."
    
    # LLM returns drifted value A = 9.9 (9.9 does NOT exist in raw_source_text)
    drifted_llm_payload = {
        "formula": "v * A",
        "variables": {"v": 4.0, "A": 9.9},
        "claimed_answer": 2.0,
        "extraction_confidence": "high"
    }
    mock_gateway = MockCalculationGateway(drifted_llm_payload)

    res = await extract_and_verify_calculation_async(raw_source_text, gateway=mock_gateway)
    
    assert res["gate_passed"] is False
    assert res["status"] == "NEEDS_REVIEW"
    assert "Verification Gate Failed" in res["summary"]
    assert "9.9" in res["summary"]

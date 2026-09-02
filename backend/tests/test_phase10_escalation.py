import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
API_KEY = "sovereignx-demo-key-2026"
HEADERS = {"X-API-Key": API_KEY}

from unittest.mock import patch

def test_high_confidence_investigation_no_escalation():
    """
    High-confidence grounded P-204 query should return requires_human_review = False.
    """
    mock_chunks = [
        {"chunk_id": "c1", "document_id": "d1", "filename": "p204.pdf", "content": "P-204 temp 91 C", "score": 0.85}
    ]
    with patch("app.agents.RAGAgent.retrieve_evidence", return_value=mock_chunks):
        response = client.post(
            "/agents/investigate",
            json={"query": "What happened to Pump P-204?"},
            headers=HEADERS
        )
        assert response.status_code == 200
        data = response.json()
        assert "confidence" in data
        assert data["confidence"] >= 0.7000
        assert data["requires_human_review"] is False
        assert data["escalation_reason"] is None

def test_low_confidence_investigation_triggers_escalation():
    """
    Weak / out-of-scope query should score < 0.7000 and return requires_human_review = True.
    """
    mock_chunks = [
        {"chunk_id": "c2", "document_id": "d2", "filename": "g7.pdf", "content": "G-7 info", "score": 0.50}
    ]
    with patch("app.agents.RAGAgent.retrieve_evidence", return_value=mock_chunks):
        response = client.post(
            "/agents/investigate",
            json={"query": "What is the coolant fluid viscosity specification for auxiliary generator G-7?"},
            headers=HEADERS
        )
        assert response.status_code == 200
        data = response.json()
        assert "confidence" in data
        assert data["confidence"] < 0.7000
        assert data["requires_human_review"] is True
        assert data["escalation_reason"] is not None
        assert "safety threshold" in data["escalation_reason"].lower()

def test_case_creation_from_escalated_investigation():
    """
    POST /cases with requires_human_review = True should automatically set status to 'Open'.
    """
    case_payload = {
        "query": "What is the coolant fluid viscosity specification for auxiliary generator G-7?",
        "answer": "The provided evidence is insufficient to specify fluid viscosity for generator G-7.",
        "asset": "Auxiliary Generator G-7",
        "confidence": 0.6672,
        "requires_human_review": True,
        "escalation_reason": "Retrieval confidence (66.7%) is below safety threshold (70.0%) — recommend manual verification before acting on this finding.",
        "retrieved_chunks": [],
        "tool_executions": []
    }
    response = client.post(
        "/cases",
        json=case_payload,
        headers=HEADERS
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "Open"
    assert data["requires_human_review"] is True
    assert data["escalation_reason"] is not None

def test_report_docx_generation_with_escalation():
    """
    DOCX generation for low-confidence response should succeed and produce valid binary stream.
    """
    payload = {
        "query": "Un-indexed asset query",
        "answer": "Weak finding with low grounding.",
        "retrieved_chunks": [],
        "confidence": 0.6500,
        "requires_human_review": True,
        "escalation_reason": "Retrieval confidence (65.0%) is below safety threshold (70.0%).",
        "tool_executions": [],
        "metadata": {"model_used": "mock", "latency_ms": 12.5}
    }
    response = client.post("/reports/generate-docx", json=payload, headers=HEADERS)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert len(response.content) > 1000

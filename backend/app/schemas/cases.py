from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class CaseCreateRequest(BaseModel):
    query: str
    answer: str
    asset: Optional[str] = "Pump P-204"
    status: Optional[str] = None
    severity: Optional[str] = "High"
    confidence: Optional[float] = 0.0
    requires_human_review: Optional[bool] = False
    escalation_reason: Optional[str] = None
    retrieved_chunks: Optional[List[Dict[str, Any]]] = []
    tool_executions: Optional[List[Dict[str, Any]]] = []

class CaseUpdateRequest(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None

class CaseResponse(BaseModel):
    id: int
    case_id: str
    asset: str
    title: str
    finding: str
    query: str
    status: str
    severity: str
    confidence: float
    requires_human_review: bool = False
    escalation_reason: Optional[str] = None
    evidence: List[Dict[str, Any]] = []
    tool_executions: List[Dict[str, Any]] = []
    retrieved_chunks: List[Dict[str, Any]] = []
    created_at: str
    updated_at: str

class CaseSummaryResponse(BaseModel):
    total: int
    open: int
    under_investigation: int
    resolved: int

class ReportRecordResponse(BaseModel):
    id: int
    report_id: str
    case_id: Optional[str] = None
    query: str
    format: str
    filename: str
    status: str
    generated_at: str

class ReportSummaryResponse(BaseModel):
    total: int
    docx: int
    pptx: int
    xlsx: int

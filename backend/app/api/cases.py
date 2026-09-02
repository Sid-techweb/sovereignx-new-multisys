import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cases_reports import SQLCase
from app.schemas.cases import CaseCreateRequest, CaseUpdateRequest, CaseResponse, CaseSummaryResponse
from app.api.auth import verify_api_key
from app.api.reports import extract_unique_citations

logger = logging.getLogger("sovereignx")
router = APIRouter(prefix="/cases", tags=["cases"])

def format_case_model(c: SQLCase) -> Dict[str, Any]:
    return {
        "id": c.id,
        "case_id": c.case_id,
        "asset": c.asset,
        "title": c.title,
        "finding": c.finding,
        "query": c.query,
        "status": c.status,
        "severity": c.severity,
        "confidence": c.confidence,
        "requires_human_review": getattr(c, "requires_human_review", False) or False,
        "escalation_reason": getattr(c, "escalation_reason", None),
        "evidence": c.evidence or [],
        "tool_executions": c.tool_executions or [],
        "retrieved_chunks": c.retrieved_chunks or [],
        "created_at": c.created_at.isoformat() if isinstance(c.created_at, datetime) else str(c.created_at),
        "updated_at": c.updated_at.isoformat() if isinstance(c.updated_at, datetime) else str(c.updated_at)
    }

@router.get("", response_model=Dict[str, Any])
async def get_cases(db: Session = Depends(get_db)):
    """
    Returns all cases and summary breakdown by status.
    """
    try:
        cases = db.query(SQLCase).order_by(SQLCase.created_at.desc()).all()
    except Exception as e:
        logger.warning(f"Error querying cases from database: {e}")
        cases = []

    case_list = [format_case_model(c) for c in cases]
    
    summary = {
        "total": len(case_list),
        "open": sum(1 for c in case_list if c["status"] == "Open"),
        "under_investigation": sum(1 for c in case_list if c["status"] == "Under Investigation"),
        "resolved": sum(1 for c in case_list if c["status"] == "Resolved")
    }
    
    return {
        "summary": summary,
        "cases": case_list
    }

@router.post("", response_model=CaseResponse, status_code=201)
async def create_case(payload: CaseCreateRequest, db: Session = Depends(get_db)):
    """
    Creates a new case record from an investigation output.
    Reuses Phase 8 extract_unique_citations to extract evidence provenance (filename, page, chunk_id).
    If confidence < 0.7000 (or requires_human_review=True), automatically sets status='Open' and sets escalation flag.
    """
    # 1. Reuse Phase 8 citation extraction
    formatted_answer, unique_citations = extract_unique_citations(payload.answer, payload.retrieved_chunks or [])
    
    # 2. Determine asset identifier
    asset = payload.asset or "Pump P-204"
    if "p-204" in payload.query.lower() or "p204" in payload.query.lower():
        asset = "Pump P-204"
    elif "c-118" in payload.query.lower() or "c118" in payload.query.lower():
        asset = "Compressor C-118"
    elif "c-900" in payload.query.lower():
        asset = "Compressor C-900"
        
    # 3. Generate unique Case ID
    case_count = db.query(SQLCase).count() if db else 0
    case_id = f"CASE-P204-00{case_count + 1}"
    
    # Create Title summary from query/answer
    title_words = payload.query.split()[:8]
    title = " ".join(title_words) if title_words else "Anomaly Investigation Case"

    # 4. Phase 10 Confidence Escalation check
    conf_val = payload.confidence if payload.confidence is not None else 0.0
    ESCALATION_THRESHOLD = 0.7000
    requires_review = bool(payload.requires_human_review) or (conf_val < ESCALATION_THRESHOLD)
    
    # Status rule: Low-confidence cases auto-created as "Open" needing review. High confidence uses specified or "Under Investigation".
    initial_status = "Open" if requires_review else (payload.status or "Under Investigation")
    
    esc_reason = payload.escalation_reason
    if requires_review and not esc_reason:
        esc_reason = f"Retrieval confidence ({conf_val * 100:.1f}%) is below safety threshold (70.0%) — recommend manual verification before acting on this finding."

    new_case = SQLCase(
        case_id=case_id,
        asset=asset,
        title=title,
        finding=formatted_answer,
        query=payload.query,
        status=initial_status,
        severity=payload.severity or ("High" if requires_review else "Medium"),
        confidence=conf_val,
        requires_human_review=requires_review,
        escalation_reason=esc_reason,
        evidence=unique_citations,
        tool_executions=payload.tool_executions or [],
        retrieved_chunks=payload.retrieved_chunks or []
    )
    
    db.add(new_case)
    db.commit()
    db.refresh(new_case)
    
    logger.info(f"Case created: {new_case.case_id} for asset {new_case.asset} (requires_human_review={new_case.requires_human_review})")
    return CaseResponse(**format_case_model(new_case))

@router.get("/{case_id}", response_model=CaseResponse)
async def get_case_detail(case_id: str, db: Session = Depends(get_db)):
    """
    Retrieves detailed case information by Case ID.
    """
    case = db.query(SQLCase).filter(SQLCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return CaseResponse(**format_case_model(case))

@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case_status_severity(case_id: str, payload: CaseUpdateRequest, db: Session = Depends(get_db)):
    """
    Updates status or severity of a case strictly via manual operator UI action.
    """
    case = db.query(SQLCase).filter(SQLCase.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
        
    if payload.status:
        if payload.status not in ["Open", "Under Investigation", "Resolved"]:
            raise HTTPException(status_code=400, detail="Invalid status value")
        case.status = payload.status
        
    if payload.severity:
        if payload.severity not in ["Low", "Medium", "High", "Critical"]:
            raise HTTPException(status_code=400, detail="Invalid severity value")
        case.severity = payload.severity
        
    db.commit()
    db.refresh(case)
    logger.info(f"Case {case_id} manually updated: status={case.status}, severity={case.severity}")
    return CaseResponse(**format_case_model(case))

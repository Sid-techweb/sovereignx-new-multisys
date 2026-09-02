import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.gateway import get_gateway, ModelGateway
from app.models.investigation_persistence import SQLInvestigationConversation, SQLInvestigationMessage
from app.api.agents import run_investigation_workflow
from app.schemas.agents import AgentInvestigateResponse

logger = logging.getLogger("sovereignx")
router = APIRouter(prefix="/investigations", tags=["investigations"])

class InvestigationMessageRequest(BaseModel):
    query: str = Field(..., min_length=1)

class InvestigationConversationResponse(BaseModel):
    conversation_id: str
    title: str
    created_at: str
    updated_at: str

@router.post("/conversations", status_code=201)
async def create_conversation(db: Session = Depends(get_db)):
    """Creates a new Investigation conversation context."""
    convo_id = str(uuid.uuid4())
    convo = SQLInvestigationConversation(
        conversation_id=convo_id,
        title="New Investigation"
    )
    db.add(convo)
    db.commit()
    db.refresh(convo)
    return {
        "conversation_id": convo.conversation_id,
        "title": convo.title,
        "created_at": convo.created_at.isoformat() if isinstance(convo.created_at, datetime) else str(convo.created_at),
        "updated_at": convo.updated_at.isoformat() if isinstance(convo.updated_at, datetime) else str(convo.updated_at)
    }

@router.post("/conversations/{conversation_id}/messages")
async def post_investigation_message(
    conversation_id: str,
    payload: InvestigationMessageRequest,
    db: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_gateway)
):
    """
    Executes the exact 4-agent investigation pipeline for a query,
    persists the query and response in PostgreSQL, and updates the conversation state.
    """
    # 1. Fetch or create conversation record
    convo = db.query(SQLInvestigationConversation).filter(
        SQLInvestigationConversation.conversation_id == conversation_id
    ).first()

    if not convo:
        title = payload.query.strip().replace("\n", " ")
        title = (title[:57] + "...") if len(title) > 60 else title
        convo = SQLInvestigationConversation(
            conversation_id=conversation_id,
            title=title
        )
        db.add(convo)
        db.commit()
        db.refresh(convo)

    # Update title if default
    if convo.title == "New Investigation":
        title = payload.query.strip().replace("\n", " ")
        convo.title = (title[:57] + "...") if len(title) > 60 else title

    # 2. Call the exact same 4-agent investigation workflow
    agent_response: AgentInvestigateResponse = await run_investigation_workflow(
        query=payload.query,
        db=db,
        gateway=gateway,
        context_id=conversation_id
    )

    # 3. Store message record
    msg = SQLInvestigationMessage(
        conversation_id=conversation_id,
        query=agent_response.query,
        answer=agent_response.answer,
        confidence=agent_response.confidence,
        retrieved_chunks=agent_response.retrieved_chunks,
        tool_executions=agent_response.tool_executions,
        metadata_json=agent_response.metadata,
        requires_human_review=agent_response.requires_human_review,
        escalation_reason=agent_response.escalation_reason
    )
    db.add(msg)
    
    # Touch conversation updated_at
    convo.updated_at = datetime.utcnow()
    db.add(convo)
    db.commit()

    # 4. Return response with conversation_id attached
    resp_dict = agent_response.model_dump()
    resp_dict["conversation_id"] = conversation_id
    return resp_dict

@router.get("/conversations")
async def list_conversations(db: Session = Depends(get_db)):
    """Lists all past investigation conversations ordered by recent activity."""
    convos = db.query(SQLInvestigationConversation).order_by(
        SQLInvestigationConversation.updated_at.desc()
    ).all()
    
    result = []
    for c in convos:
        result.append({
            "conversation_id": c.conversation_id,
            "title": c.title,
            "created_at": c.created_at.isoformat() if isinstance(c.created_at, datetime) else str(c.created_at),
            "updated_at": c.updated_at.isoformat() if isinstance(c.updated_at, datetime) else str(c.updated_at)
        })
    return result

@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    """Returns the full message history for a specific investigation conversation."""
    convo = db.query(SQLInvestigationConversation).filter(
        SQLInvestigationConversation.conversation_id == conversation_id
    ).first()

    if not convo:
        raise HTTPException(status_code=404, detail=f"Investigation conversation {conversation_id} not found.")

    messages = db.query(SQLInvestigationMessage).filter(
        SQLInvestigationMessage.conversation_id == conversation_id
    ).order_by(SQLInvestigationMessage.created_at.asc()).all()

    msg_list = []
    for m in messages:
        msg_list.append({
            "id": m.id,
            "conversation_id": m.conversation_id,
            "query": m.query,
            "answer": m.answer,
            "confidence": m.confidence,
            "retrieved_chunks": m.retrieved_chunks or [],
            "tool_executions": m.tool_executions or [],
            "metadata": m.metadata_json or {},
            "requires_human_review": m.requires_human_review,
            "escalation_reason": m.escalation_reason,
            "created_at": m.created_at.isoformat() if isinstance(m.created_at, datetime) else str(m.created_at)
        })

    return {
        "conversation_id": convo.conversation_id,
        "title": convo.title,
        "created_at": convo.created_at.isoformat() if isinstance(convo.created_at, datetime) else str(convo.created_at),
        "updated_at": convo.updated_at.isoformat() if isinstance(convo.updated_at, datetime) else str(convo.updated_at),
        "messages": msg_list
    }

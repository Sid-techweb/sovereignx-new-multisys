import json
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.gateway import get_gateway, ModelGateway
from app.gateway.exceptions import (
    UnsupportedProviderError,
    OllamaUnavailableError,
    ProviderInitializationError,
    ProviderExecutionError,
)
from app.schemas import (
    ChatTurnRequest,
    ChatTurnResponse,
    ChatMessageOut,
    ChatConversationOut,
    ChatConversationCreateResponse,
)
from app.chat.models import ChatConversation, ChatMessage
from app.chat.service import handle_chat_turn, stream_chat_turn, get_or_create_conversation, ChatServiceError

logger = logging.getLogger("sovereignx")
router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/conversations", response_model=ChatConversationCreateResponse, status_code=201)
def create_conversation(db: Session = Depends(get_db)):
    """Starts a new, empty chat conversation. A title is set from the first message sent."""
    convo = get_or_create_conversation(db, None)
    return ChatConversationCreateResponse(conversation_id=convo.conversation_id)


@router.get("/conversations", response_model=List[ChatConversationOut])
def list_conversations(db: Session = Depends(get_db)):
    """Lists all chat conversations, most recently updated first."""
    rows = db.query(ChatConversation).order_by(ChatConversation.updated_at.desc()).all()
    return [
        ChatConversationOut(
            conversation_id=c.conversation_id,
            title=c.title,
            created_at=c.created_at.isoformat() if c.created_at else "",
            updated_at=c.updated_at.isoformat() if c.updated_at else "",
        )
        for c in rows
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=List[ChatMessageOut])
def get_conversation_messages(conversation_id: str, db: Session = Depends(get_db)):
    """Returns the full message history for a conversation, in send order."""
    convo = db.query(ChatConversation).filter(
        ChatConversation.conversation_id == conversation_id
    ).first()
    if not convo:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found.")

    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [
        ChatMessageOut(
            message_id=m.message_id,
            role=m.role,
            content=m.content,
            route=m.route,
            document_id=m.document_id,
            sources=json.loads(m.sources) if m.sources else None,
            created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m in rows
    ]


@router.post("/conversations/{conversation_id}/messages", response_model=ChatTurnResponse)
async def send_message(
    conversation_id: str,
    request: ChatTurnRequest,
    db: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_gateway),
):
    """
    Sends a user message in a conversation and returns the assistant's reply.

    Automatically routes between general local-model chat, document-grounded
    RAG, and multimodal (image) answering -- the caller does not need to pick
    a mode. General chat never requires a document to exist in the knowledge
    base; RAG is only used when the message or an attached document clearly
    calls for it.
    """
    if not settings.GENERAL_CHAT_ENABLED and not request.document_id:
        raise HTTPException(
            status_code=503,
            detail="General chat is currently disabled by configuration (GENERAL_CHAT_ENABLED=false)."
        )

    try:
        result = await handle_chat_turn(
            db=db,
            gateway=gateway,
            conversation_id=conversation_id,
            user_message=request.message,
            attached_document_id=request.document_id,
        )
    except ChatServiceError as e:
        if e.category == "model_unavailable":
            raise HTTPException(status_code=503, detail=str(e))
        if e.category == "document_failure":
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except (UnsupportedProviderError, OllamaUnavailableError, ProviderInitializationError, ProviderExecutionError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat turn: {e}")
        raise HTTPException(status_code=500, detail=f"Chat request failed: {str(e)}")

    return ChatTurnResponse(
        conversation_id=result["conversation_id"],
        message_id=result["message_id"],
        route=result["route"],
        answer=result["answer"],
        retrieved_chunks=result["retrieved_chunks"],
        tool_executions=result["tool_executions"],
        rag_degraded_reason=result["rag_degraded_reason"],
        timings_ms=result["timings"],
    )


@router.post("/conversations/{conversation_id}/messages/stream")
async def send_message_stream(
    conversation_id: str,
    request: ChatTurnRequest,
    db: Session = Depends(get_db),
    gateway: ModelGateway = Depends(get_gateway),
):
    """
    Streaming counterpart to POST .../messages: returns newline-delimited
    JSON (NDJSON), one event object per line, as the model generates tokens
    -- so the UI can render the response progressively instead of waiting
    for the full answer. The existing non-streaming endpoint above is
    unchanged and continues to work exactly as before.

    Event shapes (see app/chat/service.py:stream_chat_turn for the exact
    source of truth):
      {"type": "start", "conversation_id", "route", "retrieved_chunks", "tool_executions", "rag_degraded_reason"}
      {"type": "token", "content": "..."}                          (repeated)
      {"type": "done", "message_id", "answer", "route", "timings_ms", "ollama_metadata", ...}
      {"type": "error", "category", "message", "partial_content"?}

    Because the HTTP 200 response begins streaming before generation can be
    known to succeed, errors (model unavailable, mid-generation failure,
    etc.) are delivered as an in-stream "error" event rather than an HTTP
    error status -- once bytes have started flowing, the status code can no
    longer change.
    """
    if not settings.GENERAL_CHAT_ENABLED and not request.document_id:
        raise HTTPException(
            status_code=503,
            detail="General chat is currently disabled by configuration (GENERAL_CHAT_ENABLED=false)."
        )

    async def event_stream():
        async for event in stream_chat_turn(
            db=db,
            gateway=gateway,
            conversation_id=conversation_id,
            user_message=request.message,
            attached_document_id=request.document_id,
        ):
            yield json.dumps(event) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")

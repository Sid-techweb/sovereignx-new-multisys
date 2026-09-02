from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ChatRequest(BaseModel):
    prompt: str

class ChatResponse(BaseModel):
    finding: str
    sop_reference: str
    confidence: float
    recommended_action: str


# --- General-purpose conversational chat (RAG-optional) ---

class ChatTurnRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's chat message")
    document_id: Optional[str] = Field(
        None, description="Document explicitly attached/referenced for this turn, if any"
    )

class ChatTurnResponse(BaseModel):
    conversation_id: str
    message_id: str
    route: str
    answer: str
    retrieved_chunks: List[Dict[str, Any]] = []
    tool_executions: List[Dict[str, Any]] = []
    rag_degraded_reason: Optional[str] = None
    # Set when an EXPLICIT document-grounded request (DOCUMENT_RAG route)
    # could not be grounded even after attempting the reverse Qwen->BGE
    # resource transition. When set, `answer` is a fixed, user-facing
    # "document grounding unavailable" message, NEVER an ungrounded normal
    # answer presented as if retrieval had succeeded -- see chat/service.py.
    rag_unavailable_reason: Optional[str] = None
    timings_ms: Dict[str, float] = {}

class ChatMessageOut(BaseModel):
    message_id: str
    role: str
    content: str
    route: Optional[str] = None
    document_id: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None
    created_at: str

class ChatConversationOut(BaseModel):
    conversation_id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str

class ChatConversationCreateResponse(BaseModel):
    conversation_id: str

import uuid
from sqlalchemy import Column, String, Text, DateTime, func
from app.database import Base


def _new_id() -> str:
    return str(uuid.uuid4())


class ChatConversation(Base):
    """A single chat thread. Title is derived from the first user message."""
    __tablename__ = "chat_conversations"

    conversation_id = Column(String(36), primary_key=True, default=_new_id, index=True)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    """A single message within a chat conversation, in send order."""
    __tablename__ = "chat_messages"

    message_id = Column(String(36), primary_key=True, default=_new_id, index=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "system" | "user" | "assistant"
    content = Column(Text, nullable=False)
    route = Column(String(20), nullable=True)  # GENERAL_CHAT | DOCUMENT_RAG | MULTIMODAL (assistant messages only)
    document_id = Column(String(36), nullable=True)  # document explicitly attached to this turn, if any
    sources = Column(Text, nullable=True)  # JSON-encoded list of cited chunks/sources, if any
    created_at = Column(DateTime, server_default=func.now(), index=True)

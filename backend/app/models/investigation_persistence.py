from sqlalchemy import Column, String, Integer, Float, JSON, Text, DateTime, Boolean, func
from app.database import Base

class SQLInvestigationConversation(Base):
    __tablename__ = "investigation_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(50), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False, default="New Investigation")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SQLInvestigationMessage(Base):
    __tablename__ = "investigation_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(50), index=True, nullable=False)
    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False, default=0.0)
    retrieved_chunks = Column(JSON, nullable=True)
    tool_executions = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    requires_human_review = Column(Boolean, nullable=False, default=False)
    escalation_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

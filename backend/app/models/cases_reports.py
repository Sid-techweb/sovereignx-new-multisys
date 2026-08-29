from sqlalchemy import Column, String, Integer, Float, JSON, Text, DateTime, Boolean, func
from app.database import Base

class SQLCase(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(50), unique=True, index=True, nullable=False)
    asset = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    finding = Column(Text, nullable=False)
    query = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="Open")  # Open, Under Investigation, Resolved
    severity = Column(String(50), nullable=False, default="Medium")  # Low, Medium, High, Critical
    confidence = Column(Float, nullable=False, default=0.0)
    requires_human_review = Column(Boolean, nullable=False, default=False)
    escalation_reason = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)  # List of citations: [{index, filename, page, chunk_id}]
    tool_executions = Column(JSON, nullable=True)
    retrieved_chunks = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SQLReportRecord(Base):
    __tablename__ = "report_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(50), unique=True, index=True, nullable=False)
    case_id = Column(String(50), nullable=True)
    query = Column(Text, nullable=False)
    format = Column(String(20), nullable=False)  # DOCX, PPTX, XLSX
    filename = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="Generated")
    generated_at = Column(DateTime, server_default=func.now())

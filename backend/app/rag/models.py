from sqlalchemy import Column, String, Integer, JSON, Text, DateTime, func
from pgvector.sqlalchemy import Vector
from app.database import Base

# BGE-M3 standard dense embedding dimension is 1024
BGE_M3_DIMENSION = 1024

class SQLDocumentChunk(Base):
    __tablename__ = "document_chunks"

    chunk_id = Column(String(36), primary_key=True, index=True)
    document_id = Column(String(36), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    document_checksum = Column(String(64), nullable=False)
    chunk_metadata = Column(JSON, nullable=True)  # renamed to chunk_metadata to avoid conflict with Base.metadata
    
    # pgvector embedding column.
    embedding = Column(Vector(BGE_M3_DIMENSION), nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())

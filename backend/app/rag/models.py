from sqlalchemy import Column, String, Integer, JSON, Text, DateTime, func
from pgvector.sqlalchemy import Vector
from app.database import Base

# BGE-M3 standard dense embedding dimension is 1024
BGE_M3_DIMENSION = 1024
# multilingual-e5-small dense embedding dimension is 384
E5_SMALL_DIMENSION = 384

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

    # pgvector embedding column -- BGE-M3 (v1), production default. Never
    # touched or reinterpreted by the E5 migration: a chunk's `embedding`
    # column is left exactly as it was (same type, same data, no index
    # change -- there is no ANN index on this column today; retrieval is an
    # exact ORDER BY cosine_distance scan, and stays that way for embedding_e5 too).
    embedding = Column(Vector(BGE_M3_DIMENSION), nullable=True)

    # E5 migration (v2): a SEPARATE, additive 384-dim column so a row can
    # carry both a BGE-M3 vector and a multilingual-e5-small vector at once
    # during the staged rollout -- no in-place mutation of `embedding`, no
    # forced re-upload, and instant rollback (see model_resource_manager.py /
    # embeddings.py). `embedding_e5_model` records the exact HF model id
    # that produced `embedding_e5` (not just "e5" generically), so a future
    # E5-variant swap (e.g. small -> base) can be detected/re-migrated
    # instead of silently mixing incompatible vectors under one column.
    embedding_e5 = Column(Vector(E5_SMALL_DIMENSION), nullable=True)
    embedding_e5_model = Column(String(128), nullable=True)

    created_at = Column(DateTime, server_default=func.now())

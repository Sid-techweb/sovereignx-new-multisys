import logging
from sqlalchemy.orm import Session
from app.rag.models import SQLDocumentChunk
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider
from app.rag.chunker import chunk_document
from app.rag.exceptions import IndexingError, DatabaseConnectionError
from app.schemas.documents import ExtractedDocument

logger = logging.getLogger("sovereignx")

class KnowledgeBaseIndexer:
    """
    Ingests ExtractedDocuments, processes chunking, generates embeddings, and
    saves to PostgreSQL. Provider-agnostic: writes to whichever vector
    column matches the injected (or default, config-selected) embedding
    provider -- see EmbeddingProvider.vector_column in embeddings.py.
    """
    def __init__(self, db: Session, embedding_provider: EmbeddingProvider = None):
        self.db = db
        self.embedding_provider = embedding_provider or get_embedding_provider()

    def index_document(self, doc: ExtractedDocument) -> int:
        """
        Indexes a normalized ExtractedDocument.
        Returns the count of chunks created.
        """
        # 1. Validate extraction status
        if doc.extraction_status in ["not_implemented", "failed"]:
            raise IndexingError(
                f"Document '{doc.filename}' cannot be indexed: extraction status is '{doc.extraction_status}'."
            )
            
        if not doc.content.strip():
            raise IndexingError(
                f"Document '{doc.filename}' cannot be indexed: extracted text content is empty."
            )

        # 2. Duplicate & Stale check
        checksum = doc.metadata.get("checksum_sha256") or ""
        
        # Check if already indexed with matching checksum
        try:
            existing_chunks = self.db.query(SQLDocumentChunk).filter(
                SQLDocumentChunk.document_id == doc.document_id
            ).all()
        except Exception as e:
            logger.error(f"Database query failure: {str(e)}")
            raise DatabaseConnectionError(f"Database query failed: {str(e)}") from e
        
        if existing_chunks:
            # If the checksum matches, it is already indexed. Return count of existing chunks.
            if existing_chunks[0].document_checksum == checksum:
                logger.info(f"Document {doc.filename} already indexed and unchanged. Skipping.")
                return len(existing_chunks)
            else:
                # If checksum differs, invalidate/delete existing chunks
                logger.info(f"Document {doc.filename} has changed (stale checksum). Re-indexing.")
                self.delete_document_index(doc.document_id)

        # 3. Chunk
        chunks_dto = chunk_document(
            document_id=doc.document_id,
            filename=doc.filename,
            source=doc.source,
            content=doc.content,
            metadata=doc.metadata
        )

        if not chunks_dto:
            raise IndexingError("No text chunks generated for document.")

        # 4. Generate embeddings locally via embed_documents() so any
        # provider-specific asymmetric formatting (e.g. E5's "passage: "
        # prefix) is applied without this class knowing about it.
        texts = [chunk.content for chunk in chunks_dto]
        try:
            embeddings = self.embedding_provider.embed_documents(texts)
        except Exception as e:
            logger.error(f"Failed to generate embeddings during indexing: {str(e)}")
            raise IndexingError(f"Embedding model error: {str(e)}") from e

        # 5. Store chunks + embeddings in PostgreSQL + pgvector, into
        # whichever column this provider's vectors live in. `embedding_e5_model`
        # records the exact model that produced embedding_e5 (Phase 7's
        # version metadata) -- left NULL for the BGE column, which has no
        # such per-row tracking need (it has always been exactly BGE-M3).
        try:
            for idx, chunk_dto in enumerate(chunks_dto):
                sql_chunk = SQLDocumentChunk(
                    chunk_id=chunk_dto.chunk_id,
                    document_id=chunk_dto.document_id,
                    filename=chunk_dto.filename,
                    source=chunk_dto.source,
                    content=chunk_dto.content,
                    chunk_index=chunk_dto.chunk_index,
                    page_number=chunk_dto.page_number,
                    document_checksum=checksum,
                    chunk_metadata=chunk_dto.chunk_metadata,
                )
                setattr(sql_chunk, self.embedding_provider.vector_column, embeddings[idx])
                if self.embedding_provider.vector_column == "embedding_e5":
                    sql_chunk.embedding_e5_model = self.embedding_provider.model_name
                self.db.add(sql_chunk)
            
            self.db.commit()
            logger.info(f"Indexed {len(chunks_dto)} chunks for document: {doc.filename}")
            return len(chunks_dto)
        except Exception as e:
            self.db.rollback()
            logger.error(f"Database error during indexing: {str(e)}")
            raise DatabaseConnectionError(f"Database storage failed: {str(e)}") from e

    def delete_document_index(self, document_id: str):
        """Removes all indexed chunks and embeddings for a specific document_id."""
        try:
            self.db.query(SQLDocumentChunk).filter(
                SQLDocumentChunk.document_id == document_id
            ).delete()
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete document index: {str(e)}")
            raise DatabaseConnectionError(f"Failed to delete document index: {str(e)}") from e

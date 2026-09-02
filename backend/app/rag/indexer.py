import logging
from sqlalchemy.orm import Session
from app.rag.models import SQLDocumentChunk
from app.rag.embeddings import BGEM3EmbeddingProvider
from app.rag.chunker import chunk_document
from app.rag.exceptions import IndexingError, PartialIndexingError, DatabaseConnectionError
from app.schemas.documents import ExtractedDocument

logger = logging.getLogger("sovereignx")

class KnowledgeBaseIndexer:
    """Ingests ExtractedDocuments, processes chunking, generates embeddings, and saves to PostgreSQL."""
    def __init__(self, db: Session, embedding_provider: BGEM3EmbeddingProvider = None):
        self.db = db
        self.embedding_provider = embedding_provider or BGEM3EmbeddingProvider()

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

        # 4. Generate BGE-M3 embeddings in batches & store in database
        batch_size = 10
        total_chunks = len(chunks_dto)
        total_batches = (total_chunks + batch_size - 1) // batch_size
        succeeded_chunks = 0

        for batch_idx, i in enumerate(range(0, total_chunks, batch_size), 1):
            chunk_batch = chunks_dto[i:i + batch_size]
            texts = [c.content for c in chunk_batch]
            try:
                batch_embeddings = self.embedding_provider.get_embeddings(texts)
                for idx, chunk_dto in enumerate(chunk_batch):
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
                        embedding=batch_embeddings[idx]
                    )
                    self.db.add(sql_chunk)
                self.db.commit()
                succeeded_chunks += len(chunk_batch)
                logger.info(f"Indexed batch {batch_idx}/{total_batches} ({len(chunk_batch)} chunks, cumulative {succeeded_chunks}/{total_chunks}) for {doc.filename}")
            except Exception as e:
                self.db.rollback()
                logger.error(f"Indexing failure at batch {batch_idx}/{total_batches} ({succeeded_chunks} chunks succeeded): {str(e)}")
                if succeeded_chunks > 0 or batch_idx > 1:
                    raise PartialIndexingError(
                        f"Failed at batch {batch_idx}/{total_batches}: {str(e)}",
                        failed_at_batch=batch_idx,
                        chunks_succeeded=succeeded_chunks
                    ) from e
                else:
                    raise IndexingError(f"Failed at batch 1: {str(e)}") from e

        return total_chunks

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

import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.rag.models import SQLDocumentChunk
from app.rag.embeddings import BGEM3EmbeddingProvider
from app.rag.exceptions import SearchQueryError, DatabaseConnectionError, EmbeddingModelUnavailableError
from app.config import settings

from app.services import DocumentMetadataStore

logger = logging.getLogger("sovereignx")
_metadata_store = DocumentMetadataStore()

class KnowledgeBaseRetriever:
    """Performs local vector similarity searches on PostgreSQL + pgvector using BGE-M3."""
    def __init__(self, db: Session, embedding_provider: BGEM3EmbeddingProvider = None):
        self.db = db
        self.embedding_provider = embedding_provider or BGEM3EmbeddingProvider()

    def retrieve(self, query: str, top_k: int = 5) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Executes similarity query against database.
        Returns list of relevant chunks sorted by relevance score.
        """
        if not query or not query.strip():
            raise SearchQueryError("Search query cannot be empty.")
            
        if top_k <= 0 or top_k > 20:
            raise SearchQueryError("top_k parameter must be between 1 and 20.")

        # 1. Generate query embedding locally using BGE-M3
        try:
            query_embedding = self.embedding_provider.get_embedding(query)
        except (SearchQueryError, EmbeddingModelUnavailableError):
            raise
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {str(e)}")
            raise SearchQueryError(f"Embedding model failure: {str(e)}") from e

        # 2. Retrieve similar chunks using pgvector cosine distance
        try:
            cosine_dist_expr = SQLDocumentChunk.embedding.cosine_distance(query_embedding)
            
            # cosine_distance = 1 - cosine_similarity
            # Therefore similarity_score = 1 - cosine_distance
            results = self.db.query(
                SQLDocumentChunk,
                (1.0 - cosine_dist_expr).label("similarity_score")
            ).order_by(
                cosine_dist_expr.asc()
            ).limit(top_k).all()
            
            retrieved = []
            has_raw_results = len(results) > 0
            for chunk, score in results:
                # Bounded score verification (float precision bounds)
                bounded_score = max(0.0, min(1.0, float(score)))
                relevance_percent = bounded_score * 100.0
                if relevance_percent < settings.RAG_MIN_RELEVANCE_PERCENT:
                    continue

                # Resolve original human-readable filename from DocumentMetadataStore
                doc_meta = _metadata_store.get(chunk.document_id)
                resolved_filename = (doc_meta.get("filename") if doc_meta else None) or chunk.filename

                retrieved.append({
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "filename": resolved_filename,
                    "source": chunk.source,
                    "content": chunk.content,
                    "score": round(bounded_score, 4),  # Relevance score
                    "metadata": {
                        "page_number": chunk.page_number,
                        "chunk_index": chunk.chunk_index,
                        **chunk.chunk_metadata
                    }
                })
                
            below_threshold = has_raw_results and len(retrieved) == 0
            return retrieved, below_threshold
        except Exception as e:
            logger.error(f"Database query failure during retrieval: {str(e)}")
            raise DatabaseConnectionError(f"Database query failed: {str(e)}") from e

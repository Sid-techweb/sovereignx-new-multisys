import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.rag.models import SQLDocumentChunk
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider
from app.rag.exceptions import SearchQueryError, DatabaseConnectionError, EmbeddingModelUnavailableError
from app.config import settings

logger = logging.getLogger("sovereignx")

class KnowledgeBaseRetriever:
    """
    Performs local vector similarity searches on PostgreSQL + pgvector.
    Provider-agnostic: queries whichever vector column matches the injected
    (or default, config-selected) embedding provider -- see
    EmbeddingProvider.vector_column in embeddings.py -- so this class needs
    no BGE/E5-specific branching of its own.
    """
    def __init__(self, db: Session, embedding_provider: EmbeddingProvider = None):
        self.db = db
        self.embedding_provider = embedding_provider or get_embedding_provider()

    def retrieve(self, query: str, top_k: int = 5) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Executes similarity query against database.
        Returns list of relevant chunks sorted by relevance score.
        """
        if not query or not query.strip():
            raise SearchQueryError("Search query cannot be empty.")

        if top_k <= 0 or top_k > 20:
            raise SearchQueryError("top_k parameter must be between 1 and 20.")

        # 1. Generate the query embedding locally, via embed_query() so any
        # provider-specific asymmetric formatting (e.g. E5's "query: "
        # prefix) is applied without this class knowing about it.
        try:
            query_embedding = self.embedding_provider.embed_query(query)
        except (SearchQueryError, EmbeddingModelUnavailableError):
            raise
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {str(e)}")
            raise SearchQueryError(f"Embedding model failure: {str(e)}") from e

        # 2. Retrieve similar chunks using pgvector cosine distance, against
        # whichever column this provider's vectors live in.
        try:
            vector_column = getattr(SQLDocumentChunk, self.embedding_provider.vector_column)
            cosine_dist_expr = vector_column.cosine_distance(query_embedding)

            # cosine_distance = 1 - cosine_similarity
            # Therefore similarity_score = 1 - cosine_distance
            # Excludes rows that don't yet have a vector in this provider's
            # column -- relevant mid-migration, where BGE-indexed chunks
            # may not have an embedding_e5 value yet (see migration script).
            results = self.db.query(
                SQLDocumentChunk,
                (1.0 - cosine_dist_expr).label("similarity_score")
            ).filter(
                vector_column.isnot(None)
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
                retrieved.append({
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "filename": chunk.filename,
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

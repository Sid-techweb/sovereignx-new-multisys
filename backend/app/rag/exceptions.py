class RAGError(Exception):
    """Base exception class for RAG module errors."""
    pass

class EmbeddingModelUnavailableError(RAGError):
    """Exception raised when local embedding model artifacts are not present."""
    pass

class DatabaseConnectionError(RAGError):
    """Exception raised when database connection fails or pgvector is unavailable."""
    pass

class IndexingError(RAGError):
    """Exception raised when document indexing fails or is rejected."""
    pass

class PartialIndexingError(IndexingError):
    """Exception raised when document indexing crashes mid-way after creating some chunks."""
    def __init__(self, message: str, failed_at_batch: int = 1, chunks_succeeded: int = 0):
        super().__init__(message)
        self.failed_at_batch = failed_at_batch
        self.chunks_succeeded = chunks_succeeded

class SearchQueryError(RAGError):
    """Exception raised when a similarity search query is invalid."""
    pass

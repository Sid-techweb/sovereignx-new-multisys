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

class SearchQueryError(RAGError):
    """Exception raised when a similarity search query is invalid."""
    pass

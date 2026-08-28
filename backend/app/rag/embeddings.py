import logging
from typing import List
from app.config import settings
from app.rag.exceptions import EmbeddingModelUnavailableError
from app.rag.models import BGE_M3_DIMENSION

logger = logging.getLogger("sovereignx")

class EmbeddingProvider:
    """Interface / Base class for embedding generation."""
    def get_embedding(self, text: str) -> List[float]:
        pass

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        pass


class BGEM3EmbeddingProvider(EmbeddingProvider):
    """Local offline embedding generator using BAAI/bge-m3."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        import sys
        # Disable singleton pattern during unit testing to allow mock patching and isolation
        if "pytest" in sys.modules or "unittest" in sys.modules:
            instance = super(BGEM3EmbeddingProvider, cls).__new__(cls)
            instance._initialized = False
            return instance

        if cls._instance is None:
            cls._instance = super(BGEM3EmbeddingProvider, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = None):
        if self._initialized:
            return
        self.model_name = model_name or settings.EMBEDDING_MODEL or "BAAI/bge-m3"
        self._model = None

    def initialize(self):
        if self._initialized:
            return
        
        logger.info(f"Initializing local BGE-M3 embedding model: {self.model_name}")
        try:
            from sentence_transformers import SentenceTransformer
            from sentence_transformers.sentence_transformer.modules import Transformer, Pooling
            
            # Enforce local_files_only=True to prevent network calls in air-gapped environment
            transformer = Transformer(self.model_name, model_kwargs={'local_files_only': True})
            try:
                emb_dim = transformer.get_embedding_dimension()
            except AttributeError:
                emb_dim = transformer.get_word_embedding_dimension()
                
            pooling = Pooling(emb_dim, pooling_mode='mean')
            self._model = SentenceTransformer(modules=[transformer, pooling])
            
            # Dynamically check embedding dimension to prevent mismatches
            try:
                dimension = self._model.get_embedding_dimension()
            except AttributeError:
                dimension = self._model.get_sentence_embedding_dimension()
                
            if dimension != BGE_M3_DIMENSION:
                raise ValueError(
                    f"Model output dimension {dimension} does not match database schema dimension {BGE_M3_DIMENSION}"
                )
                
            self._initialized = True
            logger.info("Local BGE-M3 model initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to load local BGE-M3 model '{self.model_name}': {str(e)}")
            raise EmbeddingModelUnavailableError(
                f"Embedding model '{self.model_name}' is not available locally. "
                f"Ensure model files are pre-downloaded to cache for air-gapped deployment. Detail: {str(e)}"
            ) from e

    def get_embedding(self, text: str) -> List[float]:
        self.initialize()
        try:
            # Generate embedding vector
            embedding = self._model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            raise RuntimeError(f"Embedding generation failed: {str(e)}") from e

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        self.initialize()
        try:
            # Generate embeddings batch
            embeddings = self._model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        except Exception as e:
            raise RuntimeError(f"Batch embedding generation failed: {str(e)}") from e

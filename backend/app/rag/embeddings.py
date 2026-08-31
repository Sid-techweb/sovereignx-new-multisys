import logging
import os
import threading
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


class _BGEM3ModelRunner(EmbeddingProvider):
    """
    The actual in-process BGE-M3 loader/runner: SentenceTransformer /
    Transformer / Pooling pipeline backed by native PyTorch state.

    THIS CLASS MUST ONLY EVER BE CONSTRUCTED INSIDE THE ISOLATED EMBEDDING
    WORKER PROCESS (see embedding_worker.py / embedding_worker_manager.py).
    A controlled investigation proved BGE-M3's native execution can SIGSEGV
    under Windows commit-charge pressure, reproducibly, independent of
    package versions -- so the main FastAPI process must never touch this
    class directly. Application code (retriever, indexer, chat service,
    API routes) should use `BGEM3EmbeddingProvider` below instead, which
    presents the same interface but delegates to the isolated worker.

    This is a true process-wide singleton *within whichever process
    constructs it* -- repeatedly constructing a fresh instance instead of
    reusing one warm instance was separately proven (via a standalone
    script) to cause intermittent native memory corruption on its own.
    """
    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(_BGEM3ModelRunner, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    @classmethod
    def reset_for_testing(cls):
        """Clears the singleton so a test can exercise a fresh, independently-mockable instance."""
        cls._instance = None

    def __init__(self, model_name: str = None):
        if self._initialized:
            return
        self.model_name = model_name or settings.EMBEDDING_MODEL or "BAAI/bge-m3"
        self._model = None

    def initialize(self):
        if self._initialized:
            return

        # Double-checked locking: within a single process, more than one
        # caller could reach initialize() before the first completes.
        with self._init_lock:
            if self._initialized:
                return
            self._initialize_locked()

    def _initialize_locked(self):
        logger.info(f"Initializing local BGE-M3 embedding model: {self.model_name}")
        try:
            # app/config.py already sets HF_HUB_OFFLINE=1 as early as possible in
            # process startup (see its top-of-file comment for why: local_files_only
            # on model_kwargs alone does not reliably suppress every huggingface_hub
            # metadata call). Re-asserted here defensively in case this provider is
            # ever exercised before app.config has been imported.
            os.environ.setdefault("HF_HUB_OFFLINE", "1")

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
            embedding = self._model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            raise RuntimeError(f"Embedding generation failed: {str(e)}") from e

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        self.initialize()
        try:
            embeddings = self._model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        except Exception as e:
            raise RuntimeError(f"Batch embedding generation failed: {str(e)}") from e


class BGEM3EmbeddingProvider(EmbeddingProvider):
    """
    Client-facing embedding provider used throughout the app (retriever,
    indexer, chat service, API routes). Presents the exact same interface
    the in-process implementation always has -- callers do not need to
    know that BGE-M3 now runs in an isolated worker process; they just
    call get_embedding()/get_embeddings() as before.

    Internally this delegates every call to the shared EmbeddingWorkerManager
    singleton, which owns the actual worker process, IPC, health tracking,
    and restart policy. See embedding_worker_manager.py for the isolation
    architecture and why it exists.
    """

    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL or "BAAI/bge-m3"

    def initialize(self):
        """Ensures the embedding worker is spawned and ready. Non-fatal by
        design at call sites that tolerate degradation (e.g. FastAPI
        startup); raises EmbeddingModelUnavailableError if the worker
        cannot become ready within the configured timeout."""
        from app.rag.embedding_worker_manager import get_worker_manager
        manager = get_worker_manager(self.model_name)
        manager.ensure_ready(timeout=settings.BGE_WORKER_STARTUP_TIMEOUT_SECONDS)

    def get_embedding(self, text: str) -> List[float]:
        vectors = self.get_embeddings([text])
        return vectors[0]

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        from app.rag.embedding_worker_manager import get_worker_manager
        manager = get_worker_manager(self.model_name)
        return manager.embed(texts)

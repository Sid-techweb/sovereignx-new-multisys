import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

# Runtime chat/RAG inference must be fully offline-capable in air-gapped
# industrial deployments. This module is imported first by virtually every
# other app module, so setting these here -- before anything else has a
# chance to import transformers/huggingface_hub/sentence-transformers --
# guarantees zero outbound network calls for local model loading regardless
# of import order elsewhere in the app. This only affects this backend
# process; the separate standalone model download/setup tooling runs in its
# own process and is unaffected. setdefault() preserves an explicit
# developer override (e.g. HF_HUB_OFFLINE=0 for a debug session).
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Find the parent directories to search for `.env`
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
ROOT_DIR = BACKEND_DIR.parent

# Check for .env in root directory or backend directory
env_path = ROOT_DIR / ".env"
if not env_path.exists():
    env_path = BACKEND_DIR / ".env"

class Settings(BaseSettings):
    MODEL_PROVIDER: str = "mock"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    MODEL_NAME: str = ""
    # How long Ollama keeps the model resident in memory after a request
    # (Ollama duration string, e.g. "30m", "1h", or "-1" to never unload).
    # A cold qwen2.5:7b load costs ~9.7s (measured); keeping it warm between
    # normal chat requests avoids paying that cost repeatedly.
    OLLAMA_KEEP_ALIVE: str = "30m"
    # Model-aware generation option, not model-specific code: some models
    # (e.g. qwen3.5:4b) support an Ollama "think" mode that emits internal
    # chain-of-thought before the answer. Benchmarking found qwen3.5:4b can
    # enter a long, non-terminating self-verification loop specifically on
    # arithmetic even with thinking disabled, and thinking mode makes every
    # response slower/more verbose across the board -- so it's off by
    # default for a chat assistant. None (the default) omits the "think"
    # field from every Ollama request entirely, which is always safe: a
    # model without thinking support (e.g. qwen2.5:7b) simply ignores an
    # unrecognized option (verified), so switching MODEL_NAME back to a
    # non-thinking model does not require also clearing this setting.
    OLLAMA_THINK: Optional[bool] = False
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173","http://localhost:5174",
    "http://127.0.0.1:5174",]
    DOCUMENT_STORAGE_PATH: str = "storage/documents"
    MAX_UPLOAD_SIZE_MB: int = 25
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/sovereignx"

    # Embedding provider selection. Switched to "e5" after the full staged
    # migration's validation gates all passed: production-path retrieval
    # (Recall@1/3/5=1.0, MRR=1.0, wrong-asset=0, matching the isolated
    # benchmark once a test-isolation confound was found and fixed),
    # multilingual sanity (3/4), worker-vs-in-process A/B (kept isolation --
    # negligible overhead), live acceptance, and a 40-call stress test (0
    # crashes, 39/40 successes). "bge" remains fully supported -- see
    # EMBEDDING_MODEL below and BGEM3EmbeddingProvider -- for instant
    # rollback (just flip this back; no code change, no data loss, the
    # embedding_e5 columns are additive and never touched the original
    # `embedding` column/data). Only this one switch changes which
    # model/index the rest of the app uses -- no embedding model name is
    # hardcoded elsewhere in RAG code.
    EMBEDDING_PROVIDER: str = "e5"  # "bge" | "e5"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    E5_EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"
    # Whether the E5 provider runs inside the same isolated worker-process
    # architecture BGE-M3 uses, or loads directly in-process. Measured
    # (Gate 13 of the migration, real production classes, 20 queries):
    # worker overhead vs in-process is negligible -- query median 30.86ms
    # in-process vs 31.71ms worker (~1ms), startup 18.1s vs 19.4s (~1.3s),
    # init commit cost 2108MB vs 2152MB (~44MB). Since in-process does NOT
    # give a *meaningful* latency/resource advantage, isolation is kept by
    # default: fault containment (a native crash takes down only the worker
    # process, never FastAPI) is worth keeping at this cost. Kept
    # configurable in case hardware/measurements differ elsewhere.
    E5_USE_ISOLATED_WORKER: bool = True
    API_KEY: str = "sovereignx-demo-key-2026"
    RAG_CHUNK_SIZE: int = 800
    RAG_CHUNK_OVERLAP: int = 120
    RAG_MIN_RELEVANCE_PERCENT: float = 60.0

    # General-purpose chat configuration (RAG-optional chatbot)
    GENERAL_CHAT_ENABLED: bool = True
    RAG_ENABLED: bool = True
    CHAT_HISTORY_MAX_MESSAGES: int = 12
    CHAT_CONTEXT_MAX_CHARS: int = 8000
    CHAT_SYSTEM_PROMPT: str = ""

    # BGE-M3 embedding worker isolation. A controlled investigation proved
    # BGE-M3's native (PyTorch) execution can SIGSEGV under Windows commit-
    # charge pressure, independent of package versions -- so it runs in a
    # separate OS process, never in-process with FastAPI. These control the
    # safety margin and failure handling around that worker. This is a
    # measured *safety margin*, not a proven exact BGE-M3 requirement:
    # investigation observed stable operation at ~6.4GB commit headroom and
    # crashes at ~0.6-1.4GB headroom; 2048MB sits conservatively below the
    # stable range, above the observed crash range.
    BGE_MIN_COMMIT_HEADROOM_MB: int = 2048
    BGE_WORKER_TIMEOUT_SECONDS: float = 30.0
    BGE_WORKER_STARTUP_TIMEOUT_SECONDS: float = 60.0
    BGE_WORKER_MAX_RESTART_ATTEMPTS: int = 3
    BGE_WORKER_RESTART_COOLDOWN_SECONDS: float = 10.0

    # multilingual-e5-small commit-headroom safety margin, used only when
    # E5_USE_ISOLATED_WORKER=True (the worker path reuses the same generic
    # preflight/guard machinery BGE-M3 uses). Deliberately much smaller than
    # BGE_MIN_COMMIT_HEADROOM_MB: E5-small's own measured resident footprint
    # (~118M params, 384-dim) is roughly an order of magnitude below BGE-M3's
    # ~1.9GB, so reusing BGE's 2048MB margin here would be needlessly
    # conservative. Not used at all in the (default) in-process E5 path --
    # see E5_USE_ISOLATED_WORKER and model_resource_manager.py.
    E5_MIN_COMMIT_HEADROOM_MB: int = 512

    # Local model resource orchestration (ModelResourceManager). A follow-up
    # investigation proved qwen2.5:7b's *load* (not BGE-M3 itself) fails
    # with a CUDA allocation error under Windows commit-charge pressure
    # caused by the BGE worker's ~1.9GB resident footprint -- measured
    # failing at ~2.15GB commit headroom, succeeding at ~5.93GB. This
    # threshold sits conservatively between those two measured points; it
    # is a safety margin, not a precisely bisected exact requirement.
    QWEN_MIN_COMMIT_HEADROOM_MB: int = 4096
    # Bounded wait for commit headroom to recover after stopping the BGE
    # worker to make room for Qwen, before giving up and letting the Ollama
    # call attempt anyway (its own existing error handling is the fallback).
    RESOURCE_RELEASE_TIMEOUT_SECONDS: float = 15.0

    # Bounded wait a chat turn gives background model warmup (see
    # app/services/readiness.py and main.py's startup_event) to finish
    # before proceeding anyway. Liveness (/health) never waits on this --
    # only an actual chat turn that arrives while warmup is still in flight
    # does, and only up to this many seconds.
    MODEL_WARMUP_WAIT_SECONDS: float = 5.0

    @field_validator("MODEL_PROVIDER")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        provider = v.lower()
        if provider not in ["mock", "ollama"]:
            raise ValueError("MODEL_PROVIDER must be either 'mock' or 'ollama'")
        return provider

    @field_validator("EMBEDDING_PROVIDER")
    @classmethod
    def validate_embedding_provider(cls, v: str) -> str:
        provider = v.lower()
        if provider not in ["bge", "e5"]:
            raise ValueError("EMBEDDING_PROVIDER must be either 'bge' or 'e5'")
        return provider

    model_config = SettingsConfigDict(
        env_file=str(env_path) if env_path.exists() else None,
        extra="ignore"
    )


settings = Settings()

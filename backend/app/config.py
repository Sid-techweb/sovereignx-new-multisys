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
    # Maximum allowed file upload size (MB) - stopgap limit set to 50MB
    MAX_UPLOAD_SIZE_MB: int = 50
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/sovereignx"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
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
    BGE_MIN_COMMIT_HEADROOM_MB: int = 256
    BGE_WORKER_TIMEOUT_SECONDS: float = 30.0
    BGE_WORKER_STARTUP_TIMEOUT_SECONDS: float = 60.0
    BGE_WORKER_MAX_RESTART_ATTEMPTS: int = 3
    BGE_WORKER_RESTART_COOLDOWN_SECONDS: float = 10.0

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

    # Multi-node foundation (NodeRegistry, see app/services/node_registry.py).
    # Distributed mode is OFF by default -- single-node (this machine) is the
    # only configuration actually exercised so far. When False, NodeRegistry
    # registers only the local node from OLLAMA_BASE_URL and never parses
    # AI_NODES_CONFIG or makes a remote call/health probe of any kind: there
    # is zero remote dependency in the default deployment. AI_NODES_CONFIG is
    # a JSON array of node definitions (see NodeRegistry.from_settings for
    # the exact shape) consulted only when distributed mode is on.
    # NODE_SHARED_SECRET authenticates node-to-node requests once a worker
    # API exists (not yet implemented -- foundation only).
    SOVEREIGN_DISTRIBUTED_MODE: bool = False
    AI_NODES_CONFIG: str = ""
    NODE_SHARED_SECRET: str = ""

    @field_validator("MODEL_PROVIDER")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        provider = v.lower()
        if provider not in ["mock", "ollama"]:
            raise ValueError("MODEL_PROVIDER must be either 'mock' or 'ollama'")
        return provider

    model_config = SettingsConfigDict(
        env_file=str(env_path) if env_path.exists() else None,
        extra="ignore"
    )


settings = Settings()

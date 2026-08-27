import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

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
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    DOCUMENT_STORAGE_PATH: str = "storage/documents"
    MAX_UPLOAD_SIZE_MB: int = 25
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/sovereignx"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    RAG_CHUNK_SIZE: int = 800
    RAG_CHUNK_OVERLAP: int = 120
    RAG_MIN_RELEVANCE_PERCENT: float = 60.0



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

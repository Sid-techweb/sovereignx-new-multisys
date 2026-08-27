from pydantic import BaseModel, model_validator
from typing import Optional, List, Dict, Any
from enum import Enum

class DocumentSource(str, Enum):
    USER_UPLOAD = "user_upload"
    INTERNAL_REPOSITORY = "internal_repository"
    FUTURE_CONNECTOR = "future_connector"

class ExtractionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    NOT_IMPLEMENTED = "not_implemented"
    PROCESSED_WITH_NO_TEXT = "processed_with_no_text"

class DocumentMetadata(BaseModel):
    document_id: str
    id: str  # Kept for compatibility with Phase 1/2 frontend
    filename: str
    file_type: str
    mime_type: str
    file_size: int
    size_bytes: int  # Kept for compatibility with Phase 1/2 frontend
    uploaded_at: str
    status: str
    source: str
    checksum_sha256: Optional[str] = None
    case_id: Optional[str] = None
    summary: Optional[str] = None
    tags: List[str] = []

    @model_validator(mode="before")
    @classmethod
    def populate_compatibility_fields(cls, data):
        if isinstance(data, dict):
            # Ensure id matches document_id
            if "id" not in data and "document_id" in data:
                data["id"] = data["document_id"]
            # Ensure size_bytes matches file_size
            if "size_bytes" not in data and "file_size" in data:
                data["size_bytes"] = data["file_size"]
        return data

class ExtractedDocument(BaseModel):
    document_id: str
    filename: str
    source: str
    content: str
    content_type: str
    extraction_status: str
    metadata: Dict[str, Any]
    created_at: str

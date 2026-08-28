import os
import uuid
import hashlib
import json
import logging
from datetime import datetime
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from app.config import settings
from app.schemas.documents import DocumentMetadata, ExtractedDocument
from app.services import LocalDocumentStorage, DocumentMetadataStore, get_extractor, ExtractionError

logger = logging.getLogger("sovereignx")
router = APIRouter()

storage = LocalDocumentStorage()
metadata_store = DocumentMetadataStore()

SUPPORTED_EXTENSIONS = {".pdf", ".csv", ".png", ".jpg", ".jpeg"}

# Map extensions to allowed MIME types/prefixes for validation
MIME_MAP = {
    ".pdf": ["application/pdf"],
    ".png": ["image/png"],
    ".jpg": ["image/jpeg"],
    ".jpeg": ["image/jpeg"],
    ".csv": ["text/csv", "text/plain", "application/csv", "application/vnd.ms-excel"]
}

@router.get("/documents", response_model=List[DocumentMetadata])
async def get_documents():
    """
    Returns a lightweight list of all document metadata records.
    """
    all_meta = metadata_store.get_all()
    # Sort by uploaded_at descending
    all_meta.sort(key=lambda x: x.get("uploaded_at", ""), reverse=True)
    return [DocumentMetadata(**m) for m in all_meta]

@router.post("/documents/upload", response_model=DocumentMetadata, status_code=201)
async def upload_document(file: UploadFile = File(...)):
    """
    Accepts multipart file upload, performs security and size validations,
    saves the file in secure storage, and creates a lightweight metadata record.
    """
    filename = file.filename
    # Prevent path traversal validation on user filename
    _, ext = os.path.splitext(filename.lower())
    
    # 1. Validate file extension
    if ext not in SUPPORTED_EXTENSIONS:
        logger.warning(f"Rejected upload of unsupported file type: {filename}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension. Allowed extensions: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
        
    # 2. Read contents to compute file size & checksum
    content = await file.read()
    file_size = len(content)
    
    # 3. Validate file size
    max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size > max_size_bytes:
        logger.warning(f"Rejected oversized file upload: {filename} ({file_size} bytes)")
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds the configured maximum limit of {settings.MAX_UPLOAD_SIZE_MB}MB."
        )
        
    # 4. Validate MIME type where practical
    if file.content_type:
        allowed_mimes = MIME_MAP[ext]
        if not any(file.content_type.startswith(m) or m in file.content_type for m in allowed_mimes):
            logger.warning(f"Rejected file {filename} with mismatching MIME type: {file.content_type}")
            raise HTTPException(
                status_code=400,
                detail=f"MIME type '{file.content_type}' is invalid for extension '{ext}'."
            )
            
    # 5. Generate unique ID & secure file storage name
    doc_id = str(uuid.uuid4())
    checksum = hashlib.sha256(content).hexdigest()
    storage_name = f"{doc_id}{ext}"
    
    try:
        # Secure local save
        storage.save(storage_name, content)
    except ValueError as e:
        logger.error(f"Security validation blocked upload: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail="Security validation: Invalid file path or name."
        )
    except Exception as e:
        logger.error(f"Storage save failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal storage error. Unable to save file."
        )
        
    uploaded_at = datetime.utcnow().isoformat() + "Z"
    
    # Check if case_id can be matched dynamically via metadata queries
    # e.g., if filename contains case_id pattern, we could map it.
    case_id = None
    if "case-001" in filename.lower() or "p-204" in filename.lower() or "c-118" in filename.lower():
        case_id = "CASE-001"
        
    doc_meta = {
        "document_id": doc_id,
        "id": doc_id,
        "filename": filename,
        "file_type": ext.lstrip("."),
        "mime_type": file.content_type or f"application/{ext.lstrip('.')}",
        "file_size": file_size,
        "size_bytes": file_size,
        "uploaded_at": uploaded_at,
        "status": "pending",
        "source": "user_upload",
        "checksum_sha256": checksum,
        "case_id": case_id,
        "summary": f"Uploaded {ext.lstrip('.').upper()} format source document.",
        "tags": [ext.lstrip(".").upper(), "Upload"]
    }
    
    metadata_store.save(doc_id, doc_meta)
    logger.info(f"Document uploaded: {doc_id} (name: {filename}, size: {file_size} bytes)")
    
    return DocumentMetadata(**doc_meta)

@router.post("/documents/{document_id}/process", response_model=DocumentMetadata)
async def process_document(document_id: str):
    """
    Triggers extraction of document content depending on its format
    and updates the ExtractedDocument payload.
    """
    meta = metadata_store.get(document_id)
    if not meta:
        raise HTTPException(
            status_code=404,
            detail=f"Document with ID {document_id} not found."
        )
        
    ext = f".{meta['file_type']}"
    storage_name = f"{document_id}{ext}"
    
    if not storage.exists(storage_name):
        raise HTTPException(
            status_code=404,
            detail="File content not found in secure storage."
        )
        
    logger.info(f"Document processing started: {document_id}")
    
    try:
        # Update state to processing
        meta["status"] = "processing"
        metadata_store.save(document_id, meta)
        
        # Load binary content
        content = storage.get(storage_name)
        
        # Extract content using the extractor factory
        logger.info(f"Extractor selected for document {document_id} with extension {ext}")
        extractor = get_extractor(ext)
        extracted_text, extra_meta = extractor.extract(content, filename=meta["filename"])
        
        # Determine appropriate status
        if not extracted_text:
            extraction_status = "processed_with_no_text"
        else:
            extraction_status = "processed"
            
        extracted_doc = ExtractedDocument(
            document_id=document_id,
            filename=meta["filename"],
            source=meta["source"],
            content=extracted_text,
            content_type="text",
            extraction_status=extraction_status,
            metadata={
                **extra_meta,
                "mime_type": meta["mime_type"],
                "file_size": meta["file_size"],
                "uploaded_at": meta["uploaded_at"],
                "checksum_sha256": meta.get("checksum_sha256"),
                "case_id": meta.get("case_id")
            },
            created_at=meta["uploaded_at"]
        )
        
        # Save extracted document content separately
        extracted_dir = storage.base_path / "extracted"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        extracted_file = extracted_dir / f"{document_id}.json"
        
        with open(extracted_file, "w", encoding="utf-8") as f:
            f.write(extracted_doc.model_dump_json())
            
        # Save updated metadata status
        meta["status"] = extraction_status
        metadata_store.save(document_id, meta)
        
        logger.info(f"Document processing completed: {document_id} (status: {extraction_status})")
        return DocumentMetadata(**meta)
        
    except ExtractionError as e:
        logger.error(f"Extraction failed for document {document_id}: {str(e)}")
        meta["status"] = "failed"
        metadata_store.save(document_id, meta)
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error processing document {document_id}: {str(e)}")
        meta["status"] = "failed"
        metadata_store.save(document_id, meta)
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )

@router.get("/documents/{document_id}", response_model=DocumentMetadata)
async def get_document_detail(document_id: str):
    """
    Retrieves detailed metadata record for a document.
    """
    meta = metadata_store.get(document_id)
    if not meta:
        raise HTTPException(
            status_code=404,
            detail=f"Document with ID {document_id} not found."
        )
    return DocumentMetadata(**meta)

@router.get("/documents/{document_id}/content", response_model=ExtractedDocument)
async def get_document_content(document_id: str):
    """
    Retrieves the full extracted text content and provenance fields of a processed document.
    """
    meta = metadata_store.get(document_id)
    if not meta:
        raise HTTPException(
            status_code=404,
            detail=f"Document with ID {document_id} not found."
        )
        
    extracted_file = storage.base_path / "extracted" / f"{document_id}.json"
    if not extracted_file.exists():
        # Return empty content with current processing state if not processed yet
        return ExtractedDocument(
            document_id=document_id,
            filename=meta["filename"],
            source=meta["source"],
            content="",
            content_type="text",
            extraction_status=meta["status"],
            metadata={
                "mime_type": meta["mime_type"],
                "file_size": meta["file_size"],
                "uploaded_at": meta["uploaded_at"],
                "checksum_sha256": meta.get("checksum_sha256"),
                "case_id": meta.get("case_id")
            },
            created_at=meta["uploaded_at"]
        )
        
    try:
        with open(extracted_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return ExtractedDocument(**data)
    except Exception as e:
        logger.error(f"Failed to load extracted content for document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Unable to load extracted text content."
        )

import os
import uuid
import hashlib
import json
import logging
from datetime import datetime
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.config import settings
from app.schemas.documents import DocumentMetadata, ExtractedDocument, DocumentDeleteResponse
from app.services import LocalDocumentStorage, DocumentMetadataStore, get_extractor, ExtractionError
from app.rag.models import SQLDocumentChunk
from app.rag.exceptions import PartialIndexingError
from app.rag.embeddings import BGEM3EmbeddingProvider
from app.rag.indexer import KnowledgeBaseIndexer
from app.services.model_resource_manager import get_resource_manager
from app.models.cases_reports import SQLCase, SQLReportRecord
from app.models.investigation_persistence import SQLInvestigationConversation, SQLInvestigationMessage
from app.chat.models import ChatConversation, ChatMessage

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

def execute_auto_indexing(document_id: str):
    """
    Background worker executing full document extraction, chunking, and BGE-M3 embedding generation.
    Updates DocumentMetadata store status to 'indexing', 'indexed', 'failed_partial', or 'failed'.
    """
    db = SessionLocal()
    try:
        meta = metadata_store.get(document_id)
        if not meta:
            logger.error(f"Auto-indexing failed: document {document_id} metadata not found.")
            return

        meta["status"] = "indexing"
        meta["error_message"] = None
        metadata_store.save(document_id, meta)

        ext = f".{meta['file_type']}"
        storage_name = f"{document_id}{ext}"
        try:
            target_path = storage._get_secure_path(storage_name)
        except Exception as e:
            logger.error(f"Secure path resolution failed for {document_id}: {str(e)}")
            meta["status"] = "failed"
            meta["error_message"] = f"Storage error: {str(e)}"
            metadata_store.save(document_id, meta)
            return

        # 1. Extraction Phase (reuses pre-extracted JSON if present)
        safe_doc_id = os.path.basename(document_id)
        extracted_dir = (storage.base_path / "extracted").resolve()
        extracted_file = extracted_dir / f"{safe_doc_id}.json"
        extracted_doc = None

        if extracted_file.exists():
            try:
                extracted_doc = storage.get_extracted_document(document_id)
                if extracted_doc and (extracted_doc.extraction_status in ["failed", "not_implemented"] or not extracted_doc.content.strip()):
                    logger.info(f"Ignoring stale/failed cached extraction file for {document_id}")
                    extracted_doc = None
            except Exception:
                extracted_doc = None

        if not extracted_doc:
            try:
                content_bytes = storage.get(storage_name)
                extractor = get_extractor(ext)
                extracted_text, extra_meta = extractor.extract(content_bytes, filename=meta["filename"])
                
                extraction_status = "processed_with_no_text" if not extracted_text else "processed"
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
                
                extracted_dir.mkdir(parents=True, exist_ok=True)
                with open(extracted_file, "w", encoding="utf-8") as f:
                    json.dump(extracted_doc.dict(), f, indent=2)
            except Exception as e:
                logger.exception(f"Auto-extraction failed for document {document_id}: {str(e)}")
                meta["status"] = "failed"
                meta["error_message"] = f"Extraction failed: {str(e)}"
                metadata_store.save(document_id, meta)
                return

        # 2. Indexing Phase (Chunking + Embedding Generation)
        try:
            get_resource_manager().ensure_embedding_available(timeout=settings.BGE_WORKER_STARTUP_TIMEOUT_SECONDS)
            embedder = BGEM3EmbeddingProvider()
            indexer = KnowledgeBaseIndexer(db, embedder)
            chunks_count = indexer.index_document(extracted_doc)

            meta["status"] = "indexed"
            meta["chunks_count"] = chunks_count
            meta["failed_at_batch"] = None
            meta["chunks_succeeded"] = None
            meta["error_message"] = None
            metadata_store.save(document_id, meta)
            logger.info(f"Auto-indexing completed successfully for {document_id} ({chunks_count} chunks)")
        except PartialIndexingError as e:
            logger.exception(f"Auto-indexing partial failure for {document_id}: {str(e)}")
            meta["status"] = "failed_partial"
            meta["failed_at_batch"] = e.failed_at_batch
            meta["chunks_succeeded"] = e.chunks_succeeded
            meta["error_message"] = str(e)
            metadata_store.save(document_id, meta)
        except Exception as e:
            logger.exception(f"Auto-indexing failed for {document_id}: {str(e)}")
            meta["status"] = "failed"
            meta["error_message"] = f"Indexing failed: {str(e)}"
            metadata_store.save(document_id, meta)
    except Exception as top_e:
        logger.exception(f"Top-level unhandled exception in execute_auto_indexing for {document_id}: {str(top_e)}")
        try:
            meta = metadata_store.get(document_id)
            if meta:
                meta["status"] = "failed"
                meta["error_message"] = f"System error: {str(top_e)}"
                metadata_store.save(document_id, meta)
        except Exception:
            pass
    finally:
        db.close()

@router.post("/documents/upload", response_model=DocumentMetadata, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    Accepts multipart file upload, performs security and size validations,
    saves the file in secure storage, and enqueues automatic background chunking & indexing.
    """
    filename = file.filename
    _, ext = os.path.splitext(filename.lower())
    
    # 1. Validate file extension
    if ext not in SUPPORTED_EXTENSIONS:
        logger.warning(f"Rejected upload of unsupported file type: {filename}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension. Allowed extensions: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
        
    # 2. Validate MIME type where practical
    if file.content_type:
        allowed_mimes = MIME_MAP[ext]
        if not any(file.content_type.startswith(m) or m in file.content_type for m in allowed_mimes):
            logger.warning(f"Rejected file {filename} with mismatching MIME type: {file.content_type}")
            raise HTTPException(
                status_code=400,
                detail=f"MIME type '{file.content_type}' is invalid for extension '{ext}'."
            )
            
    # 3. Generate unique ID & secure file storage name
    doc_id = str(uuid.uuid4())
    storage_name = f"{doc_id}{ext}"
    try:
        target_path = storage._get_secure_path(storage_name)
    except ValueError as e:
        logger.error(f"Security validation blocked upload: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail="Security validation: Invalid file path or name."
        )

    # 4. Stream upload to disk in chunks (O(1) memory footprint)
    max_size_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    chunk_size = 2 * 1024 * 1024
    file_size = 0
    sha256_hash = hashlib.sha256()

    try:
        with open(target_path, "wb") as f_out:
            while chunk := await file.read(chunk_size):
                file_size += len(chunk)
                if file_size > max_size_bytes:
                    f_out.close()
                    if target_path.exists():
                        os.remove(target_path)
                    logger.warning(f"Rejected oversized file upload: {filename} ({file_size} bytes)")
                    raise HTTPException(
                        status_code=413,
                        detail=f"File size exceeds the configured maximum limit of {settings.MAX_UPLOAD_SIZE_MB}MB."
                    )
                sha256_hash.update(chunk)
                f_out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if target_path.exists():
            os.remove(target_path)
        logger.error(f"Storage save failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal storage error. Unable to save file."
        )

    checksum = sha256_hash.hexdigest()
    uploaded_at = datetime.utcnow().isoformat() + "Z"
    
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
        "status": "uploaded",
        "source": "user_upload",
        "checksum_sha256": checksum,
        "case_id": case_id,
        "summary": f"Uploaded {ext.lstrip('.').upper()} format source document.",
        "tags": [ext.lstrip(".").upper(), "Upload"]
    }
    
    metadata_store.save(doc_id, doc_meta)
    logger.info(f"Document uploaded: {doc_id} (name: {filename}, size: {file_size} bytes). Enqueuing auto-indexing.")
    
    # Enqueue background extraction, chunking, and embedding generation
    background_tasks.add_task(execute_auto_indexing, doc_id)

    return DocumentMetadata(**doc_meta)

@router.post("/documents/{document_id}/reindex", response_model=DocumentMetadata)
async def reindex_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Manual retry endpoint for failed or failed_partial documents.
    Clears any partially-indexed chunks from PostgreSQL pgvector, resets status to 'indexing',
    and enqueues auto-indexing from scratch.
    """
    meta = metadata_store.get(document_id)
    if not meta:
        raise HTTPException(
            status_code=404,
            detail=f"Document with ID {document_id} not found."
        )

    # 1. Atomic partial chunk cleanup from pgvector store
    try:
        deleted_count = db.query(SQLDocumentChunk).filter(SQLDocumentChunk.document_id == document_id).delete()
        db.commit()
        logger.info(f"Reindex requested for {document_id}: deleted {deleted_count} existing/partial chunks from pgvector.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to clear partial chunks during reindex: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear partial chunks: {str(e)}"
        )

    # 2. Purge stale extracted json file if present so reindex extracts fresh text
    safe_doc_id = os.path.basename(document_id)
    extracted_dir = (storage.base_path / "extracted").resolve()
    extracted_file = (extracted_dir / f"{safe_doc_id}.json").resolve()
    if extracted_file.exists():
        try:
            os.remove(extracted_file)
            logger.info(f"Purged stale extracted json file for document {document_id}")
        except Exception as e:
            logger.warning(f"Failed to remove extracted file during reindex: {e}")

    # 3. Reset status & error fields
    meta["status"] = "indexing"
    meta["failed_at_batch"] = None
    meta["chunks_succeeded"] = None
    meta["error_message"] = None
    metadata_store.save(document_id, meta)

    # 3. Enqueue background auto-indexing
    background_tasks.add_task(execute_auto_indexing, document_id)

    return DocumentMetadata(**meta)

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
        
        # Save extracted document content separately using sanitized path
        safe_doc_id = os.path.basename(document_id)
        extracted_dir = (storage.base_path / "extracted").resolve()
        extracted_dir.mkdir(parents=True, exist_ok=True)
        extracted_file = (extracted_dir / f"{safe_doc_id}.json").resolve()
        if not extracted_file.is_relative_to(extracted_dir):
            raise HTTPException(status_code=400, detail="Path traversal attempt detected.")
        
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
        
    safe_doc_id = os.path.basename(document_id)
    extracted_dir = (storage.base_path / "extracted").resolve()
    extracted_file = (extracted_dir / f"{safe_doc_id}.json").resolve()
    if not extracted_file.is_relative_to(extracted_dir):
        raise HTTPException(status_code=400, detail="Path traversal attempt detected.")
    if not extracted_file.exists():
        ext = f".{meta['file_type']}"
        storage_name = f"{document_id}{ext}"
        if storage.exists(storage_name):
            try:
                content_bytes = storage.get(storage_name)
                extractor = get_extractor(ext)
                extracted_text, extra_meta = extractor.extract(content_bytes, filename=meta["filename"])
                extraction_status = "processed_with_no_text" if not extracted_text else "processed"
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
                extracted_dir.mkdir(parents=True, exist_ok=True)
                with open(extracted_file, "w", encoding="utf-8") as f:
                    json.dump(extracted_doc.model_dump(), f, indent=2)
                return extracted_doc
            except Exception as e:
                logger.error(f"On-the-fly extraction fallback failed for {document_id}: {str(e)}")

        # Return empty content with current processing state if file not present in storage
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

@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(document_id: str, db: Session = Depends(get_db)):
    """
    Deletes a document:
    1. Removes all chunks from pgvector (knowledge_base table).
    2. Server-side provenance check against reports, cases, investigation messages, and chat messages.
    3. Removes physical file from local storage, extracted json file, and metadata record.
    4. Returns deletion status along with list of reports and cases citing this document.
    """
    meta = metadata_store.get(document_id)
    if not meta:
        raise HTTPException(
            status_code=404,
            detail=f"Document with ID {document_id} not found."
        )

    filename = meta.get("filename", "")

    # Server-side guard: Protect core CASE-001 system documents and internal repository assets
    protected_filenames = {
        "pump_P204_SOP.pdf",
        "pump_P204_sensor_data.csv",
        "pump_P204_inspection_report.pdf",
        "pump_P204_past_incident_report.pdf",
        "pump_P204_photo.jpg",
        "compressor_C118_vibration_data.csv"
    }

    if meta.get("is_protected") or meta.get("source") == "internal_repository" or filename in protected_filenames:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Document '{filename}' is a protected system asset and cannot be deleted."
        )

    # 1. Count and delete chunks from pgvector
    chunks_deleted = 0
    try:
        chunks = db.query(SQLDocumentChunk).filter(SQLDocumentChunk.document_id == document_id).all()
        chunks_deleted = len(chunks)
        if chunks_deleted > 0:
            db.query(SQLDocumentChunk).filter(SQLDocumentChunk.document_id == document_id).delete(synchronize_session=False)
            db.commit()
            logger.info(f"Deleted {chunks_deleted} pgvector chunks for document {document_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error removing pgvector chunks for document {document_id}: {e}")

    # 2. Server-side citation provenance check across reports, cases, investigation messages, and chats
    cited_in_reports = []
    cited_in_cases = []

    try:
        # Check SQLReportRecord
        reports = db.query(SQLReportRecord).all()
        for r in reports:
            raw_citations = getattr(r, "citations", []) or []
            report_title = getattr(r, "filename", getattr(r, "title", "Report"))
            is_cited = False
            if isinstance(raw_citations, list):
                for c in raw_citations:
                    if isinstance(c, dict):
                        if c.get("document_id") == document_id or c.get("filename") == filename:
                            is_cited = True
                            break
                    elif isinstance(c, str) and (document_id in c or (filename and filename in c)):
                        is_cited = True
                        break
            if is_cited and report_title not in cited_in_reports:
                cited_in_reports.append(report_title)

        # Check SQLCase
        cases = db.query(SQLCase).all()
        for case in cases:
            raw_evidence = str(getattr(case, "evidence", "") or "")
            if document_id in raw_evidence or (filename and filename in raw_evidence):
                case_name = f"Case {case.case_id}: {case.title}" if case.title else f"Case {case.case_id}"
                if case_name not in cited_in_cases:
                    cited_in_cases.append(case_name)

        # Check SQLInvestigationMessage
        inv_msgs = db.query(SQLInvestigationMessage).filter(SQLInvestigationMessage.role == "assistant").all()
        for m in inv_msgs:
            content = m.content or ""
            if document_id in content or (filename and filename in content):
                conv = db.query(SQLInvestigationConversation).filter(SQLInvestigationConversation.id == m.conversation_id).first()
                title = conv.title if conv else "Investigation Message"
                if title not in cited_in_cases:
                    cited_in_cases.append(title)

        # Check ChatMessage (read-only coverage)
        chat_msgs = db.query(ChatMessage).filter(ChatMessage.role == "assistant").all()
        for m in chat_msgs:
            content = m.content or ""
            if document_id in content or (filename and filename in content):
                conv = db.query(ChatConversation).filter(ChatConversation.id == m.conversation_id).first()
                title = f"Chat: {conv.title}" if conv else "Chat Conversation"
                if title not in cited_in_cases:
                    cited_in_cases.append(title)

    except Exception as e:
        logger.warning(f"Error checking document citation provenance for {document_id}: {e}")

    # 3. Delete physical storage file & extracted JSON
    ext = f".{meta.get('file_type', '')}"
    storage_name = f"{document_id}{ext}"
    if storage.exists(storage_name):
        storage.delete(storage_name)

    safe_doc_id = os.path.basename(document_id)
    extracted_dir = (storage.base_path / "extracted").resolve()
    extracted_file = (extracted_dir / f"{safe_doc_id}.json").resolve()
    if extracted_file.exists():
        try:
            os.remove(extracted_file)
        except Exception as e:
            logger.warning(f"Error removing extracted file {extracted_file}: {e}")

    # 4. Remove metadata record
    metadata_store.delete(document_id)
    logger.info(f"Document {document_id} ({filename}) deleted successfully.")

    return DocumentDeleteResponse(
        message="Document deleted successfully",
        document_id=document_id,
        filename=filename,
        chunks_deleted=chunks_deleted,
        cited_in_reports=cited_in_reports,
        cited_in_cases=cited_in_cases
    )

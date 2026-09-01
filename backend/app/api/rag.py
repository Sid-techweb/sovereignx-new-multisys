from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from app.database import get_db
from app.config import settings
from app.rag.models import SQLDocumentChunk
from app.rag.embeddings import get_embedding_provider
from app.rag.indexer import KnowledgeBaseIndexer
from app.rag.retriever import KnowledgeBaseRetriever
from app.rag.exceptions import IndexingError, SearchQueryError, EmbeddingModelUnavailableError, DatabaseConnectionError
from app.services.metadata_store import DocumentMetadataStore
from app.services.storage import LocalDocumentStorage
from app.services.model_resource_manager import get_resource_manager

router = APIRouter(prefix="/knowledge-base", tags=["RAG & Knowledge Base"])

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Text query to search for.")
    top_k: int = Field(5, ge=1, le=20, description="Number of results to return.")

class SearchResultItem(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    source: str
    content: str
    score: float
    metadata: Dict[str, Any]

class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem]
    below_threshold: bool = False

class IndexResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    chunks_created: int

class StatusResponse(BaseModel):
    documents_indexed: int
    chunks_indexed: int
    embedding_model: str
    vector_store: str
    index_status: str

@router.post("/index/{document_id}", response_model=IndexResponse, status_code=status.HTTP_201_CREATED)
def index_document(document_id: str, db: Session = Depends(get_db)):
    """Chuncks a processed document, generates offline BGE-M3 embeddings, and saves to pgvector."""
    # 1. Locate the document metadata
    meta_store = DocumentMetadataStore(settings.DOCUMENT_STORAGE_PATH)
    meta_data = meta_store.get(document_id)
    if not meta_data:
        raise HTTPException(status_code=404, detail=f"Document {document_id} metadata record not found.")

    # 2. Get normalized content block
    storage = LocalDocumentStorage(settings.DOCUMENT_STORAGE_PATH)
    try:
        extracted_doc = storage.get_extracted_document(document_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=400, 
            detail=f"Extracted content file for document {document_id} not found. Process document first."
        )

    # 3. Index document
    try:
        # Ingestion embeds the whole document in one batched call (see
        # KnowledgeBaseIndexer), so this ensures the worker is up once per
        # document, not per chunk. Lock-coordinated against Qwen-preemption.
        get_resource_manager().ensure_embedding_available(timeout=settings.BGE_WORKER_STARTUP_TIMEOUT_SECONDS)
        embedder = get_embedding_provider()
        indexer = KnowledgeBaseIndexer(db, embedder)
        chunks_count = indexer.index_document(extracted_doc)
        
        return IndexResponse(
            document_id=document_id,
            filename=meta_data.get("filename", "unknown"),
            status="indexed",
            chunks_created=chunks_count
        )
    except IndexingError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except EmbeddingModelUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed internally: {str(e)}")

@router.get("", response_model=StatusResponse)
def get_status(db: Session = Depends(get_db)):
    """Returns general knowledge base size stats and provider configurations."""
    try:
        doc_count = db.query(SQLDocumentChunk.document_id).distinct().count()
        chunk_count = db.query(SQLDocumentChunk).count()
        
        active_model = settings.E5_EMBEDDING_MODEL if settings.EMBEDDING_PROVIDER == "e5" else settings.EMBEDDING_MODEL
        return StatusResponse(
            documents_indexed=doc_count,
            chunks_indexed=chunk_count,
            embedding_model=active_model or "BAAI/bge-m3",
            vector_store="postgresql+pgvector",
            index_status="ready"
        )
    except Exception as e:
        raise DatabaseConnectionError(f"Vector store database connection failed: {str(e)}")

@router.post("/search", response_model=SearchResponse)
def search_knowledge_base(req: SearchRequest, db: Session = Depends(get_db)):
    """Simulates localized pgvector search query returning sorted relevant evidence."""
    try:
        embedder = get_embedding_provider()
        retriever = KnowledgeBaseRetriever(db, embedder)
        results, below_threshold = retriever.retrieve(req.query, req.top_k)
        
        return SearchResponse(
            query=req.query,
            results=results,
            below_threshold=below_threshold
        )
    except SearchQueryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except EmbeddingModelUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

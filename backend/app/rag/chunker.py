import uuid
from typing import List, Dict, Any
from app.config import settings

class DocumentChunkDTO:
    """Data Transfer Object representing a normalized chunk."""
    def __init__(
        self,
        chunk_id: str,
        document_id: str,
        filename: str,
        source: str,
        content: str,
        chunk_index: int,
        page_number: int = None,
        chunk_metadata: Dict[str, Any] = None
    ):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.filename = filename
        self.source = source
        self.content = content
        self.chunk_index = chunk_index
        self.page_number = page_number
        self.chunk_metadata = chunk_metadata or {}

def chunk_document(
    document_id: str,
    filename: str,
    source: str,
    content: str,
    metadata: Dict[str, Any],
    chunk_size: int = None,
    chunk_overlap: int = None
) -> List[DocumentChunkDTO]:
    """
    Deterministic chunking strategy.
    Configurable chunk size and overlap, preserves provenance and page numbers (for PDFs).
    """
    if chunk_size is None:
        chunk_size = settings.RAG_CHUNK_SIZE
    if chunk_overlap is None:
        chunk_overlap = settings.RAG_CHUNK_OVERLAP

    chunks = []
    chunk_index = 0
    file_type = filename.split(".")[-1].lower()

    if file_type == "pdf" and "page_count" in metadata:
        # PDF page-level split using explicit page boundary separator
        if "---SOVEREIGNX-PAGE-BREAK---" in content:
            pages = content.split("\n\n---SOVEREIGNX-PAGE-BREAK---\n\n")
        else:
            pages = content.split("\n\n")
        for page_idx, page_content in enumerate(pages):
            page_num = page_idx + 1
            page_content = page_content.strip()
            if not page_content:
                continue
            
            # Chunk the page text
            page_chunks = split_text(page_content, chunk_size, chunk_overlap)
            for p_chunk in page_chunks:
                chunks.append(
                    DocumentChunkDTO(
                        chunk_id=str(uuid.uuid4()),
                        document_id=document_id,
                        filename=filename,
                        source=source,
                        content=p_chunk,
                        chunk_index=chunk_index,
                        page_number=page_num,
                        chunk_metadata={"page_number": page_num}
                    )
                )
                chunk_index += 1
    else:
        # Default text/CSV chunking (no page number)
        paragraphs = content.split("\n\n")
        current_chunk_text = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            if len(para) > chunk_size:
                # If a single paragraph is too large, split it and flush existing
                if current_chunk_text:
                    chunks.append(
                        DocumentChunkDTO(
                            chunk_id=str(uuid.uuid4()),
                            document_id=document_id,
                            filename=filename,
                            source=source,
                            content=current_chunk_text.strip(),
                            chunk_index=chunk_index,
                            page_number=None,
                            chunk_metadata={}
                        )
                    )
                    chunk_index += 1
                    current_chunk_text = ""
                
                # Split large paragraph
                sub_chunks = split_text(para, chunk_size, chunk_overlap)
                for sc in sub_chunks:
                    chunks.append(
                        DocumentChunkDTO(
                            chunk_id=str(uuid.uuid4()),
                            document_id=document_id,
                            filename=filename,
                            source=source,
                            content=sc,
                            chunk_index=chunk_index,
                            page_number=None,
                            chunk_metadata={}
                        )
                    )
                    chunk_index += 1
            else:
                if len(current_chunk_text) + len(para) + 2 > chunk_size:
                    chunks.append(
                        DocumentChunkDTO(
                            chunk_id=str(uuid.uuid4()),
                            document_id=document_id,
                            filename=filename,
                            source=source,
                            content=current_chunk_text.strip(),
                            chunk_index=chunk_index,
                            page_number=None,
                            chunk_metadata={}
                        )
                    )
                    chunk_index += 1
                    
                    # Handle overlap by taking tail of the current chunk
                    overlap_start = max(0, len(current_chunk_text) - chunk_overlap)
                    overlap_chars = current_chunk_text[overlap_start:]
                    current_chunk_text = overlap_chars + "\n\n" + para
                else:
                    if current_chunk_text:
                        current_chunk_text += "\n\n" + para
                    else:
                        current_chunk_text = para
        
        if current_chunk_text.strip():
            chunks.append(
                DocumentChunkDTO(
                    chunk_id=str(uuid.uuid4()),
                    document_id=document_id,
                    filename=filename,
                    source=source,
                    content=current_chunk_text.strip(),
                    chunk_index=chunk_index,
                    page_number=None,
                    chunk_metadata={}
                )
            )
            
    if file_type in ["png", "jpg", "jpeg"]:
        for chunk in chunks:
            chunk.page_number = 1
            chunk.chunk_metadata["page_number"] = 1

    return chunks

def split_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """Helper to split a large block of text into overlapping substrings using word/character boundaries."""
    if len(text) <= chunk_size:
        return [text]
        
    sub_chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            sub_chunks.append(text[start:])
            break
            
        # Try to find last space or punctuation to avoid splitting mid-word
        cut = end
        for i in range(end, max(start, end - 100), -1):
            if text[i] in [' ', '\n', '.', ',', ';', '?', '!']:
                cut = i + 1
                break
        
        sub_chunks.append(text[start:cut].strip())
        start = cut - chunk_overlap
        # Safety to prevent infinite loops
        if start <= 0 or start >= cut:
            start = cut
            
    return [sc for sc in sub_chunks if sc]

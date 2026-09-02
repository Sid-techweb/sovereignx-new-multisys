import re
from typing import List, Dict, Any, Tuple

def clean_answer_text(text: str) -> str:
    """Strips raw [Source: ...] bracketed metadata strings from LLM output."""
    if not text:
        return ""
    cleaned = re.sub(r'\[Source:\s*[^\]]+\]', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'\[[^\]]*?(?:document_id|chunk_id|chunk_index|page=)[^\]]*?\]', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    cleaned = re.sub(r'\s+([.,!?;:])', r'\1', cleaned)
    return cleaned.strip()

def build_grounding_prompt(query: str, retrieved_chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Constructs the identical system prompt and user prompt used for evidence-grounded queries.
    Reused across both POST /models/grounded-query and the Analysis Agent.
    """
    system_prompt = (
        "You are a factual, evidence-grounded industrial analysis assistant.\n"
        "Your task is to answer the user's question relying ONLY on the provided evidence.\n"
        "Do not use outside knowledge. Do not extrapolate, assume, or fabricate facts.\n\n"
        "STRICT WRITING & CITATION RULES:\n"
        "1. You must write the response in clean, professional, clear natural language.\n"
        "2. Do NOT embed raw metadata, document IDs, chunk IDs, page indices, or bracketed [Source: ...] tags inside your response text.\n"
        "3. Absolute separation of evidence and metadata: state observed measurements and SOP limits clearly in text. The UI presents source document citations separately.\n"
        "4. If the provided evidence is insufficient to answer the question, state: \"The provided evidence is insufficient to answer the question.\""
    )

    prompt_parts = []
    prompt_parts.append("EVIDENCE CHUNKS:\n")
    if not retrieved_chunks:
        prompt_parts.append("[No evidence found in the knowledge base]\n")
    else:
        for idx, chunk in enumerate(retrieved_chunks, start=1):
            filename = chunk.get("filename", "unknown_file")
            doc_id = chunk.get("document_id", "unknown_id")
            chunk_id = chunk.get("chunk_id", "unknown_chunk_id")
            page_num = chunk.get("metadata", {}).get("page_number", None)
            chunk_idx = chunk.get("metadata", {}).get("chunk_index", None)
            content = chunk.get("content", "").strip()
            
            provenance_info = f"Source: {filename} | document_id={doc_id} | chunk_id={chunk_id}"
            if page_num is not None:
                provenance_info += f" | page={page_num}"
            if chunk_idx is not None:
                provenance_info += f" | chunk_index={chunk_idx}"
                
            prompt_parts.append(
                f"--- Evidence Chunk {idx} ( [{provenance_info}] ) ---\n"
                f"Content:\n{content}\n"
            )
            
    prompt_parts.append(f"\nUser Question: {query}\n")
    prompt_parts.append("\nAnswer cleanly in natural language:")
    full_prompt = "".join(prompt_parts)

    return system_prompt, full_prompt

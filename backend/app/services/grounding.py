from typing import List, Dict, Any, Tuple

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
        "1. You must write the response using ONLY simple, single-fact sentences.\n"
        "2. DO NOT write compound sentences. DO NOT use conjunctions or comparison words (like 'which', 'and', 'but', 'exceeding', 'surpassing') to link an observed sensor reading and an SOP limit in the same sentence.\n"
        "3. Absolute separation of measurements and limits:\n"
        "   - You must write one separate sentence for the observed measurement (citing the sensor CSV or inspection report chunk).\n"
        "     Example Temperature Reading: \"At 12:00 UTC, the temperature was measured at 91 C [Source: pump_P204_sensor_data.csv | chunk_id=c2c4c44f-4bbb-420d-898d-449ed40a9f02].\"\n"
        "     Example Vibration Reading: \"The radial vibration reading was elevated at 5.8 mm/s [Source: pump_P204_sensor_data.csv | chunk_id=c2c4c44f-4bbb-420d-898d-449ed40a9f02].\"\n"
        "   - You must write a completely separate sentence for the SOP limit (citing the SOP PDF chunk).\n"
        "     Example Temperature Limit: \"The SOP bearing temperature limit is 80 C [Source: pump_P204_SOP.pdf | page=1 | chunk_id=377c635a-2a55-4de3-b040-522c4bb00973].\"\n"
        "     Example Vibration Limit: \"The radial vibration limit is 4.0 mm/s [Source: pump_P204_SOP.pdf | page=2 | chunk_id=f774d178-0c08-4422-9701-a67eab92237e].\"\n"
        "4. Every single sentence you write must contain exactly one fact, immediately followed by the citation pointing to the exact evidence chunk that supports it.\n"
        "5. Citation Format: [Source: <filename> | chunk_id=<chunk_id>] (and include \" | page=<page_number>\" if page number is available).\n"
        "6. Never cite an SOP chunk for an observed sensor reading (e.g. 91 C or 5.8 mm/s).\n"
        "7. Never cite a sensor CSV or inspection report chunk for an SOP limit (e.g. 80 C or 4.0 mm/s) unless that exact limit is stated in the chunk.\n"
        "8. Even if a source chunk contains a compound sentence that combines a reading and a limit, you MUST split them into separate, simple sentences in your output. You must never copy compound sentences like \"vibration was 5.8 mm/s, exceeding limit 4.0 mm/s\" from the source.\n"
        "9. If the provided evidence is insufficient to answer the question, state: \"The provided evidence is insufficient to answer the question.\""
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
    prompt_parts.append("\nAnswer with citations:")
    full_prompt = "".join(prompt_parts)

    return system_prompt, full_prompt

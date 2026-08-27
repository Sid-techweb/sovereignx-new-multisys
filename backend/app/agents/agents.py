import re
import logging
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.rag.models import SQLDocumentChunk
from app.rag.retriever import KnowledgeBaseRetriever
from app.rag.embeddings import BGEM3EmbeddingProvider
from app.gateway import ModelGateway
from app.services.tools import LocalToolRegistry
from app.services.grounding import build_grounding_prompt

logger = logging.getLogger("sovereignx")

# --- Generic Metric Extractors ---

def extract_temperature_metrics(chunks: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    reading = None
    limit = None
    
    # Try to find temperature_c: <num> in CSV or measured temperature in text
    csv_pattern = re.compile(r"temperature_c:\s*([0-9.]+)", re.IGNORECASE)
    text_reading_pattern = re.compile(r"temperature(?:_c)?\s*(?:was|measured\s*at|reading\s*was|reading\s*was\s*measured\s*at)\s*([0-9.]+)", re.IGNORECASE)
    # Try to find temperature limit: <num>, avoiding asset IDs like P-204, supporting matching across newlines
    limit_pattern = re.compile(r"temperature(?:_c)?\s*(?:bearing\s*housing\s*)?(?:limit|threshold|maximum|permitted).{0,100}?\b(?<!P-)(?<!Pump P-)(?<!INC-)(?<!INS-)([0-9.]+)\b", re.IGNORECASE | re.DOTALL)
    
    for chunk in chunks:
        content = chunk.get("content", "")
        # Look for CSV structure
        csv_matches = csv_pattern.findall(content)
        if csv_matches:
            reading = float(csv_matches[-1])
        else:
            text_matches = text_reading_pattern.findall(content)
            if text_matches:
                reading = float(text_matches[0])
                
        limit_matches = limit_pattern.findall(content)
        if limit_matches:
            limit = float(limit_matches[0])
            
    if reading is not None and limit is not None:
        return {"reading": reading, "limit": limit}
    return None

def extract_vibration_metrics(chunks: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    reading = None
    limit = None
    
    # Try to find vibration_mm_s: <num> in CSV or measured vibration in text
    csv_pattern = re.compile(r"vibration_mm_s:\s*([0-9.]+)", re.IGNORECASE)
    text_reading_pattern = re.compile(r"vibration\s*(?:was|measured\s*at|reading\s*was|reading\s*was\s*elevated\s*at)\s*([0-9.]+)", re.IGNORECASE)
    # Try to find vibration limit: <num>, avoiding asset IDs like P-204, supporting matching across newlines
    limit_pattern = re.compile(r"vibration\s*(?:limits|limit|threshold|maximum|permissible).{0,100}?\b(?<!P-)(?<!Pump P-)(?<!INC-)(?<!INS-)([0-9.]+)\b", re.IGNORECASE | re.DOTALL)
    
    for chunk in chunks:
        content = chunk.get("content", "")
        csv_matches = csv_pattern.findall(content)
        if csv_matches:
            reading = float(csv_matches[-1])
        else:
            text_matches = text_reading_pattern.findall(content)
            if text_matches:
                reading = float(text_matches[0])
                
        limit_matches = limit_pattern.findall(content)
        if limit_matches:
            limit = float(limit_matches[0])
            
    if reading is not None and limit is not None:
        return {"reading": reading, "limit": limit}
    return None


# --- The Four Agents ---

class IntakeAgent:
    def verify_evidence_availability(self, db: Session) -> bool:
        """
        Generically verifies if the knowledge base contains indexed documents/evidence.
        If no document chunks are present in the SQL database, returns False.
        """
        try:
            count = db.query(SQLDocumentChunk).count()
            return count > 0
        except Exception as e:
            logger.error(f"Error checking evidence availability: {e}")
            return False


class RAGAgent:
    def __init__(self, db: Session):
        self.db = db
        self.embedder = BGEM3EmbeddingProvider()
        self.retriever = KnowledgeBaseRetriever(self.db, self.embedder)
        
    def retrieve_evidence(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves evidence chunks from the vector store using the existing retriever.
        """
        results, below_threshold = self.retriever.retrieve(query, top_k=top_k)
        return results


class AnalysisAgent:
    def __init__(self, gateway: ModelGateway):
        self.gateway = gateway
        self.tool_registry = LocalToolRegistry()

    async def analyze(self, query: str, retrieved_chunks: List[Dict[str, Any]], context_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates the grounded answer using the proven Stage 1 prompt & generate() pathway.
        Then, dynamically parses the evidence to execute relevant Phase 6 comparison tools.
        """
        # Reusing the exact proven system prompt from Stage 1 via shared helper
        system_prompt, full_prompt = build_grounding_prompt(query, retrieved_chunks)

        # Print the literal prompt string sent to Qwen2.5-7B-Instruct
        print("\n--- LITERAL PROMPT SENT TO OLLAMA START ---")
        print(f"SYSTEM PROMPT:\n{system_prompt}\n")
        print(f"USER PROMPT:\n{full_prompt}")
        print("--- LITERAL PROMPT SENT TO OLLAMA END ---\n")

        # Code reference proving reuse: calling the identical gateway generate pathway
        answer = await self.gateway.generate(prompt=full_prompt, system_prompt=system_prompt)

        # Tool execution matching readings and limits dynamically via regex
        tool_executions = []
        
        # Dynamic Extraction: Temperature
        temp_metrics = extract_temperature_metrics(retrieved_chunks)
        if temp_metrics:
            logger.info(f"Dynamically executing temperature comparison: {temp_metrics}")
            tool_resp = self.tool_registry.execute(
                tool_name="compare_reading_against_sop_limit",
                arguments={
                    "reading_value": temp_metrics["reading"],
                    "limit_value": temp_metrics["limit"],
                    "comparison_type": "greater_than",
                    "unit": "C"
                },
                context_id=context_id
            )
            tool_executions.append(tool_resp.model_dump())

        # Dynamic Extraction: Vibration
        vib_metrics = extract_vibration_metrics(retrieved_chunks)
        if vib_metrics:
            logger.info(f"Dynamically executing vibration comparison: {vib_metrics}")
            tool_resp = self.tool_registry.execute(
                tool_name="compare_reading_against_sop_limit",
                arguments={
                    "reading_value": vib_metrics["reading"],
                    "limit_value": vib_metrics["limit"],
                    "comparison_type": "greater_than",
                    "unit": "mm/s"
                },
                context_id=context_id
            )
            tool_executions.append(tool_resp.model_dump())

        return {
            "answer": answer,
            "tool_executions": tool_executions
        }


class ReportAgent:
    def format_report(
        self,
        query: str,
        answer: str,
        retrieved_chunks: List[Dict[str, Any]],
        tool_executions: List[Dict[str, Any]],
        model_used: str,
        latency_ms: float
    ) -> Dict[str, Any]:
        """
        Assembles response components into a clean structured report format.
        Calculates a deterministic confidence score: average similarity score of the chunks.
        """
        if not retrieved_chunks:
            confidence = 0.0
        else:
            scores = [chunk.get("score", 0.0) for chunk in retrieved_chunks]
            confidence = sum(scores) / len(scores)

        confidence = round(confidence, 4)

        return {
            "query": query,
            "answer": answer,
            "retrieved_chunks": retrieved_chunks,
            "confidence": confidence,
            "tool_executions": tool_executions,
            "metadata": {
                "model_used": model_used,
                "latency_ms": round(latency_ms, 2)
            }
        }

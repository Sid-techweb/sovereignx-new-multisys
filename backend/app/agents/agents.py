import re
import logging
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.rag.models import SQLDocumentChunk
from app.rag.retriever import KnowledgeBaseRetriever
from app.rag.embeddings import get_embedding_provider
from app.gateway import ModelGateway
from app.services.tools import LocalToolRegistry
from app.services.grounding import build_grounding_prompt
from app.tools.calculation_verifier import extract_and_verify_calculation_async

logger = logging.getLogger("sovereignx")

# --- Generic Metric Extractors ---

def extract_temperature_metrics(chunks: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    reading = None
    limit = None
    
    # Try to find temperature_c: <num> in CSV or measured temperature in text
    csv_pattern = re.compile(r"temperature_c:\s*([0-9.]+)", re.IGNORECASE)
    text_reading_pattern = re.compile(r"temperature[s]?(?:_c)?\s*(?:was|measured\s*at|reading\s*was|reading\s*was\s*measured\s*at|peaked\s*at|peaking\s*at|recorded\s*at|logged\s*at|reached|reached\s*at|registered|registered\s*at)\s*([0-9.]+)", re.IGNORECASE)
    
    # Bidirectional limit patterns
    limit_pattern_1 = re.compile(r"temperature(?:_c)?\s*(?:bearing\s*housing\s*)?(?:limit|threshold|maximum|permitted).{0,100}?\b(?<!P-)(?<!Pump P-)(?<!INC-)(?<!INS-)([0-9.]+)\b", re.IGNORECASE | re.DOTALL)
    limit_pattern_2 = re.compile(r"temperature(?:_c)?\s*(?:bearing\s*housing\s*)?.{0,100}?\b(?<!P-)(?<!Pump P-)(?<!INC-)(?<!INS-)([0-9.]+)\b\s*(?:C|F)?\s*(?:limit|threshold|maximum|permitted)", re.IGNORECASE | re.DOTALL)
    
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
                
        limit_matches = limit_pattern_1.findall(content)
        if limit_matches:
            limit = float(limit_matches[0])
        else:
            limit_matches = limit_pattern_2.findall(content)
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
    text_reading_pattern = re.compile(r"vibration[s]?\s*(?:was|were|measured\s*at|reading\s*was|reading\s*was\s*elevated\s*at|recorded\s*at|readings\s*were\s*recorded\s*at|reached|reached\s*at|registered|registered\s*at)\s*([0-9.]+)", re.IGNORECASE)
    
    # Bidirectional limit patterns
    limit_pattern_1 = re.compile(r"vibration\s*(?:limits|limit|threshold|maximum|permissible).{0,100}?\b(?<!P-)(?<!Pump P-)(?<!INC-)(?<!INS-)([0-9.]+)\b", re.IGNORECASE | re.DOTALL)
    limit_pattern_2 = re.compile(r"vibration\s*.{0,100}?\b(?<!P-)(?<!Pump P-)(?<!INC-)(?<!INS-)([0-9.]+)\b\s*(?:mm/s)?\s*(?:standard)?\s*(?:limits|limit|threshold|maximum|permissible)", re.IGNORECASE | re.DOTALL)
    
    for chunk in chunks:
        content = chunk.get("content", "")
        csv_matches = csv_pattern.findall(content)
        if csv_matches:
            reading = float(csv_matches[-1])
        else:
            text_matches = text_reading_pattern.findall(content)
            if text_matches:
                reading = float(text_matches[0])
                
        limit_matches = limit_pattern_1.findall(content)
        if limit_matches:
            limit = float(limit_matches[0])
        else:
            limit_matches = limit_pattern_2.findall(content)
            if limit_matches:
                limit = float(limit_matches[0])
            
    if reading is not None and limit is not None:
        return {"reading": reading, "limit": limit}
    return None


def is_calculation_check_query(query: str) -> bool:
    """
    Detection logic for identifying calculation verification requests.
    Checks for calculation keywords ('verify calculation', 'check formula', etc.)
    or mathematical variable equations with assignments and operators.
    """
    q = query.lower()
    calc_keywords = [
        "verify calculation", "check calculation", "verify formula", "check formula",
        "verify equation", "check equation", "verify math", "check math", "calculate formula",
        "claimed answer", "computed answer"
    ]
    if any(kw in q for kw in calc_keywords):
        return True
    
    # Pattern check: equation with "=" and numeric assignment or arithmetic operator
    if "=" in q and re.search(r'\b[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*[0-9]+', q) and re.search(r'[\+\-\*\/\^]', q):
        return True

    return False


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
        self.embedder = get_embedding_provider()
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
        Or routes calculation-check requests to the calculation verification tool path.
        """
        # Step 3 Task 1: Check if request is a calculation verification query
        if is_calculation_check_query(query):
            logger.info("Calculation-check request detected. Routing to verify_engineering_calculation tool path.")
            
            # Execute calculation verification with LLM gateway & safe AST evaluator
            calc_res = await extract_and_verify_calculation_async(query, gateway=self.gateway)
            
            # Register execution in LocalToolRegistry for audit logging
            tool_resp = self.tool_registry.execute(
                tool_name="verify_engineering_calculation",
                arguments={"text_input": query},
                context_id=context_id
            )
            
            status = calc_res.get("status", "NEEDS_REVIEW")
            formula = calc_res.get("formula") or "N/A"
            claimed = calc_res.get("claimed") if calc_res.get("claimed") is not None else "N/A"
            computed = calc_res.get("computed") if calc_res.get("computed") is not None else "N/A"
            delta = calc_res.get("delta") if calc_res.get("delta") is not None else "N/A"
            extraction_method = calc_res.get("extraction_method", "regex_fallback")
            summary = calc_res.get("summary", "")

            # Formatted Tool Result Table string
            table_header = "| METRIC | CLAIMED | COMPUTED | DELTA | RESULT |\n|---|---|---|---|---|\n"
            table_row = f"| Formula: `{formula}` | `{claimed}` | `{computed}` | `{delta}` | **{status}** |\n"
            
            formatted_answer = (
                f"### Engineering Calculation Verification\n\n"
                f"{table_header}{table_row}\n"
                f"**Extraction Method**: `{extraction_method}`\n\n"
                f"**Summary**: {summary}"
            )

            # Ensure tool execution entry has the rich outputs dictionary
            tool_exec_entry = tool_resp.model_dump()
            tool_exec_entry["outputs"] = calc_res

            return {
                "answer": formatted_answer,
                "tool_executions": [tool_exec_entry]
            }

        # NON-CALCULATION PATH: Reusing exact proven system prompt and workflow
        system_prompt, full_prompt = build_grounding_prompt(query, retrieved_chunks)

        try:
            print("\n--- LITERAL PROMPT SENT TO OLLAMA START ---")
            print(f"SYSTEM PROMPT:\n{system_prompt}\n")
            print(f"USER PROMPT:\n{full_prompt}")
            print("--- LITERAL PROMPT SENT TO OLLAMA END ---\n")
        except UnicodeEncodeError:
            import sys
            enc = sys.stdout.encoding or "utf-8"
            print("\n--- LITERAL PROMPT SENT TO OLLAMA START ---")
            print(f"SYSTEM PROMPT:\n{system_prompt.encode(enc, errors='replace').decode(enc)}\n")
            print(f"USER PROMPT:\n{full_prompt.encode(enc, errors='replace').decode(enc)}")
            print("--- LITERAL PROMPT SENT TO OLLAMA END ---\n")

        answer = await self.gateway.generate(prompt=full_prompt, system_prompt=system_prompt)

        # Parse cited chunk IDs from the LLM answer text
        cited_chunk_ids = set(re.findall(r'chunk_id=([a-f0-9\-]+)', answer))
        cited_chunks = [c for c in retrieved_chunks if c.get("chunk_id") in cited_chunk_ids]

        tool_executions = []
        
        # Dynamic Extraction: Temperature
        temp_metrics = extract_temperature_metrics(cited_chunks)
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
        vib_metrics = extract_vibration_metrics(cited_chunks)
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

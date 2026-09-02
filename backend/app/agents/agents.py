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
from app.services.grounding import build_grounding_prompt, clean_answer_text
from app.tools.calculation_verifier import extract_and_verify_calculation_async

logger = logging.getLogger("sovereignx")

# --- Generic Metric Extractors ---

def extract_temperature_metrics(chunks: List[Dict[str, Any]], query: str = "") -> Optional[Dict[str, float]]:
    reading = None
    limit = None
    
    # Try to find temperature_c: <num> in CSV or measured temperature in text or query
    csv_pattern = re.compile(r"temperature_c:\s*([0-9.]+)", re.IGNORECASE)
    text_reading_pattern = re.compile(r"temperature[s]?(?:_c)?\s*(?:was|measured\s*at|reading\s*was|reading\s*was\s*measured\s*at|peaked\s*at|peaking\s*at|recorded\s*at|logged\s*at|reached|reached\s*at|registered|registered\s*at|=\s*|:\s*|\bis\b)\s*([0-9.]+)", re.IGNORECASE)
    
    # Bidirectional limit patterns
    limit_pattern_1 = re.compile(r"temperature(?:_c)?\s*(?:bearing\s*housing\s*)?(?:limit|threshold|maximum|permitted).{0,100}?\b(?<!P-)(?<!Pump P-)(?<!INC-)(?<!INS-)([0-9.]+)\b", re.IGNORECASE | re.DOTALL)
    limit_pattern_2 = re.compile(r"temperature(?:_c)?\s*(?:bearing\s*housing\s*)?.{0,100}?\b(?<!P-)(?<!Pump P-)(?<!INC-)(?<!INS-)([0-9.]+)\b\s*(?:C|F)?\s*(?:limit|threshold|maximum|permitted)", re.IGNORECASE | re.DOTALL)
    limit_pattern_3 = re.compile(r"(?:limit|threshold|maximum|permitted|max)\s*(?:permitted|housing|bearing)*\s*temperature\s*(?:is|=|:|\s)\s*([0-9.]+)", re.IGNORECASE)

    all_texts = [chunk.get("content", "") for chunk in chunks]
    if query:
        all_texts.insert(0, query)

    for content in all_texts:
        # Look for CSV structure
        csv_matches = csv_pattern.findall(content)
        if csv_matches and reading is None:
            reading = float(csv_matches[-1])
        else:
            text_matches = text_reading_pattern.findall(content)
            if text_matches and reading is None:
                reading = float(text_matches[0])
                
        if limit is None:
            limit_matches = limit_pattern_1.findall(content)
            if limit_matches:
                limit = float(limit_matches[0])
            else:
                limit_matches = limit_pattern_2.findall(content)
                if limit_matches:
                    limit = float(limit_matches[0])
                else:
                    limit_matches = limit_pattern_3.findall(content)
                    if limit_matches:
                        limit = float(limit_matches[0])
            
    if reading is not None and limit is not None:
        return {"reading": reading, "limit": limit}
    return None

def extract_vibration_metrics(chunks: List[Dict[str, Any]], query: str = "") -> Optional[Dict[str, float]]:
    reading = None
    limit = None
    
    # Try to find vibration_mm_s: <num> in CSV or measured vibration in text or query
    csv_pattern = re.compile(r"vibration_mm_s:\s*([0-9.]+)", re.IGNORECASE)
    text_reading_pattern = re.compile(r"vibration[s]?\s*(?:was|were|measured\s*at|reading\s*was|reading\s*was\s*elevated\s*at|recorded\s*at|readings\s*were\s*recorded\s*at|reached|reached\s*at|registered|registered\s*at|=\s*|:\s*|\bis\b)\s*([0-9.]+)", re.IGNORECASE)
    
    # Bidirectional limit patterns
    limit_pattern_1 = re.compile(r"vibration\s*(?:limits|limit|threshold|maximum|permissible).{0,100}?\b(?<!P-)(?<!Pump P-)(?<!INC-)(?<!INS-)([0-9.]+)\b", re.IGNORECASE | re.DOTALL)
    limit_pattern_2 = re.compile(r"vibration\s*.{0,100}?\b(?<!P-)(?<!Pump P-)(?<!INC-)(?<!INS-)([0-9.]+)\b\s*(?:mm/s)?\s*(?:standard)?\s*(?:limits|limit|threshold|maximum|permissible)", re.IGNORECASE | re.DOTALL)
    limit_pattern_3 = re.compile(r"(?:limit|threshold|maximum|permitted|permissible|max)\s*(?:permitted|standard)*\s*vibration\s*(?:is|=|:|\s)\s*([0-9.]+)", re.IGNORECASE)

    all_texts = [chunk.get("content", "") for chunk in chunks]
    if query:
        all_texts.insert(0, query)

    for content in all_texts:
        csv_matches = csv_pattern.findall(content)
        if csv_matches and reading is None:
            reading = float(csv_matches[-1])
        else:
            text_matches = text_reading_pattern.findall(content)
            if text_matches and reading is None:
                reading = float(text_matches[0])
                
        if limit is None:
            limit_matches = limit_pattern_1.findall(content)
            if limit_matches:
                limit = float(limit_matches[0])
            else:
                limit_matches = limit_pattern_2.findall(content)
                if limit_matches:
                    limit = float(limit_matches[0])
                else:
                    limit_matches = limit_pattern_3.findall(content)
                    if limit_matches:
                        limit = float(limit_matches[0])
            
    if reading is not None and limit is not None:
        return {"reading": reading, "limit": limit}
    return None


def is_calculation_check_query(query: str) -> bool:
    """
    Intent-based detection logic for genuine calculation verification / engineering math requests.
    Identifies calculation requests based on calculation intent phrases (e.g. 'calculate pump efficiency',
    'verify calculation', 'check formula', 'calculate pressure drop') or mathematical variable equations
    with real arithmetic operators on the RHS of an assignment (e.g. P = F / A, Q = K * sqrt(dp)).
    Does NOT trigger on plain reading statements like 'temperature = 91 C', negative readings like 'vibration = -0.5 mm/s',
    equipment tags like 'P-204', or SOP limit comparison queries.
    """
    q = query.lower()
    
    # 1. Intent-based regex for calculation / formula verification phrases
    calc_intent_pattern = re.compile(
        r'\b(verify|check|calculate|eval|evaluate)\b.{0,60}?\b(calculat\w*|formula|equation|math\w*|efficiency|pressure drop|head loss|power|flow rate|claimed answer|computed answer|result)\b',
        re.IGNORECASE | re.DOTALL
    )
    if calc_intent_pattern.search(q):
        return True

    # 2. Check for explicit arithmetic assignment: var = expression
    # RHS must contain real arithmetic operators (*, /, +, ^, binary -) or math functions (sqrt, log, abs)
    # Excludes plain assignments like 'temperature = 91 C', negative readings like 'vibration = -0.5 mm/s', or equipment IDs like 'P-204'
    eq_match = re.search(r'\b[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*(.+)', q)
    if eq_match:
        rhs = eq_match.group(1).strip()
        # Clean unit slashes like mm/s, m/s, ft/s, kg/m3 so they are not misread as arithmetic division
        rhs_clean = re.sub(r'\b[a-zA-Z]+/[a-zA-Z0-9]+\b', '', rhs)
        has_binary_sub = bool(re.search(r'\b[a-zA-Z0-9.]+\s+[\-]\s+[a-zA-Z0-9.]+\b', rhs_clean))
        has_operator = bool(re.search(r'[\*\/\^\+]', rhs_clean)) or has_binary_sub
        has_math_func = bool(re.search(r'\b(sqrt|log|abs|sin|cos|tan)\s*\(', rhs_clean))
        
        # Ensure RHS isn't just a plain number/negative number + unit or plain text statement
        if (has_operator or has_math_func) and not re.match(r'^-?[0-9.]+\s*[a-zA-Z/%]*$', rhs_clean):
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

        # Parse cited chunk IDs from the LLM answer text if present
        cited_chunk_ids = set(re.findall(r'chunk_id=([a-f0-9\-]+)', answer))
        cited_chunks = [c for c in retrieved_chunks if c.get("chunk_id") in cited_chunk_ids]
        if not cited_chunks:
            cited_chunks = retrieved_chunks

        # Clean raw [Source: ...] bracketed metadata tags from answer text
        cleaned_answer = clean_answer_text(answer)

        tool_executions = []
        
        # Dynamic Extraction: Temperature
        temp_metrics = extract_temperature_metrics(cited_chunks, query=query)
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
        vib_metrics = extract_vibration_metrics(cited_chunks, query=query)
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
            "answer": cleaned_answer,
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

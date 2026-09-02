from typing import List, Dict, Optional, AsyncGenerator
from app.gateway.base import ModelGateway, StreamChunk
from app.schemas.analysis import AnalysisRequest, AnalysisResponse

class MockGateway(ModelGateway):
    async def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        """
        Implements ModelGateway to return a static, realistic document-analysis
        response for Phase 1 testing and prototyping.
        """
        return AnalysisResponse(
            finding="Bearing housing temperature exceeds the specified SOP threshold.",
            sop_reference="Maintenance SOP Section 4.2",
            confidence=0.87,
            recommended_action="Inspect lubrication and bearing clearance."
        )

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        """
        Implements ModelGateway to return a static grounded query response
        for test/mock validation environments.
        """
        return (
            "Based on the provided maintenance records, Pump P-204 experienced "
            "abnormal housing temperatures at 12:00 UTC on August 12, 2026, "
            "as logged in [pump_P204_sensor_data.csv]."
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        options: Optional[Dict] = None
    ) -> str:
        """
        Implements ModelGateway to return a static, deterministic conversational
        reply for mock/testing environments without requiring a local model.
        """
        last_user_message = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            ""
        )
        return f"[mock reply] Acknowledged: {last_user_message}"

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        options: Optional[Dict] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Implements the streaming counterpart by yielding the same mock reply
        word-by-word, so streaming call sites can be tested without Ollama.
        """
        full_text = await self.chat_completion(messages, options)
        words = full_text.split(" ")
        for i, word in enumerate(words):
            delta = word if i == 0 else f" {word}"
            yield StreamChunk(content=delta, done=False, metadata=None)
        yield StreamChunk(
            content="",
            done=True,
            metadata={
                "total_duration_ms": 1.0,
                "load_duration_ms": 0.0,
                "prompt_eval_duration_ms": 0.0,
                "eval_duration_ms": 1.0,
                "prompt_eval_count": 0,
                "eval_count": len(words),
            }
        )


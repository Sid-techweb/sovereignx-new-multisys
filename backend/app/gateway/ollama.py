import json
import logging
from typing import List, Dict, Optional, AsyncGenerator
import httpx
from app.gateway.base import ModelGateway, StreamChunk
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.gateway.exceptions import OllamaUnavailableError, ProviderExecutionError

logger = logging.getLogger("sovereignx")

class OllamaGateway(ModelGateway):
    def __init__(
        self,
        base_url: str,
        model_name: str,
        keep_alive: Optional[str] = None,
        think: Optional[bool] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name or "qwen2.5:7b"
        # Ollama duration string (e.g. "30m") controlling how long the model
        # stays resident after a request. None lets Ollama use its own
        # default (5 minutes) rather than sending the field at all.
        self.keep_alive = keep_alive
        # Model-aware, not model-specific: a config-driven generation option
        # (see Settings.OLLAMA_THINK) rather than a per-model branch in this
        # gateway. None omits the "think" field entirely, which is always
        # safe to do for any model. Applied uniformly to every chat route
        # (GENERAL_CHAT/DOCUMENT_RAG/EXISTING_TOOL_FLOW/MULTIMODAL all share
        # chat_completion/stream_chat_completion below), so no route gets
        # inconsistent generation behavior.
        self.think = think

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        """
        Sends the text prompt to the local Ollama server's /api/generate endpoint.
        Returns the raw generated text response.
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 512
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            logger.info(f"Sending prompt to Ollama model '{self.model_name}' at {url}")
            async with httpx.AsyncClient(timeout=300.0) as client:
                res = await client.post(url, json=payload)
                
            if res.status_code != 200:
                logger.error(f"Ollama returned HTTP error status: {res.status_code}")
                raise ProviderExecutionError(f"Ollama server returned HTTP {res.status_code}: {res.text}")
                
            data = res.json()
            return data.get("response", "")
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Ollama server: {str(e)}")
            raise OllamaUnavailableError(
                f"Could not connect to Ollama server at {self.base_url}. "
                "Ensure Ollama is running and server is healthy."
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error calling Ollama generate: {str(e)}")
            raise ProviderExecutionError(f"Ollama execution failed: {str(e)}") from e

    async def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        """
        Asynchronously calls the local Ollama server's generation endpoint forcing JSON formatting.
        Parses and returns structured AnalysisResponse.
        """
        prompt = (
            f"Analyze the following industrial finding:\n{request.input_text}\n\n"
            "You must return a JSON object with the following fields:\n"
            "- 'finding': A string summarizing the core issue/finding.\n"
            "- 'sop_reference': A string indicating the relevant SOP section (or 'N/A' if unknown).\n"
            "- 'confidence': A float between 0.0 and 1.0 indicating your confidence score.\n"
            "- 'recommended_action': A string proposing a fix or action item.\n"
        )
        
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }
        
        try:
            logger.info(f"Sending analysis request to Ollama model '{self.model_name}' (JSON mode)")
            async with httpx.AsyncClient(timeout=300.0) as client:
                res = await client.post(url, json=payload)
                
            if res.status_code != 200:
                raise ProviderExecutionError(f"Ollama server returned HTTP {res.status_code}: {res.text}")
                
            data = res.json()
            response_text = data.get("response", "{}")
            
            parsed_json = json.loads(response_text)
            return AnalysisResponse(
                finding=parsed_json.get("finding", "Unknown finding"),
                sop_reference=parsed_json.get("sop_reference", "N/A"),
                confidence=float(parsed_json.get("confidence", 0.5)),
                recommended_action=parsed_json.get("recommended_action", "No action specified")
            )
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Ollama server: {str(e)}")
            raise OllamaUnavailableError(
                f"Could not connect to Ollama server at {self.base_url}. "
                "Ensure Ollama is running and server is healthy."
            ) from e
        except Exception as e:
            logger.error(f"Error parsing Ollama response: {str(e)}")
            raise ProviderExecutionError(f"Failed to process model response: {str(e)}") from e

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        options: Optional[Dict] = None
    ) -> str:
        """
        Sends a multi-turn conversation to the local Ollama server's native
        /api/chat endpoint, which understands role-tagged message history
        directly (no manual prompt flattening required).
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 1024,
                **(options or {})
            }
        }
        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive
        if self.think is not None:
            payload["think"] = self.think

        try:
            logger.info(f"Sending chat completion to Ollama model '{self.model_name}' ({len(messages)} messages)")
            async with httpx.AsyncClient(timeout=300.0) as client:
                res = await client.post(url, json=payload)

            if res.status_code != 200:
                logger.error(f"Ollama returned HTTP error status: {res.status_code}")
                raise ProviderExecutionError(f"Ollama server returned HTTP {res.status_code}: {res.text}")

            data = res.json()
            return data.get("message", {}).get("content", "")
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Ollama server: {str(e)}")
            raise OllamaUnavailableError(
                f"Could not connect to Ollama server at {self.base_url}. "
                "Ensure Ollama is running and server is healthy."
            ) from e
        except (OllamaUnavailableError, ProviderExecutionError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Ollama chat completion: {str(e)}")
            raise ProviderExecutionError(f"Ollama chat completion failed: {str(e)}") from e

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        options: Optional[Dict] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Sends a multi-turn conversation to Ollama's /api/chat with stream=true
        and yields incremental StreamChunks as tokens arrive. The final chunk
        has done=True and carries Ollama's own timing/token-count metadata
        (converted to milliseconds), so callers do not lose the ability to
        diagnose latency just because the response is streamed.
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.3,
                "num_predict": 1024,
                **(options or {})
            }
        }
        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive
        if self.think is not None:
            payload["think"] = self.think

        logger.info(f"Sending streaming chat completion to Ollama model '{self.model_name}' ({len(messages)} messages)")
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", url, json=payload) as res:
                    if res.status_code != 200:
                        body = await res.aread()
                        logger.error(f"Ollama returned HTTP error status: {res.status_code}")
                        raise ProviderExecutionError(f"Ollama server returned HTTP {res.status_code}: {body!r}")

                    async for line in res.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning(f"Skipping unparseable Ollama stream line: {line!r}")
                            continue

                        if data.get("error"):
                            raise ProviderExecutionError(f"Ollama streaming error: {data['error']}")

                        delta = data.get("message", {}).get("content", "")
                        is_done = bool(data.get("done"))

                        if not is_done:
                            if delta:
                                yield StreamChunk(content=delta, done=False, metadata=None)
                            continue

                        metadata = {
                            "total_duration_ms": data.get("total_duration", 0) / 1e6,
                            "load_duration_ms": data.get("load_duration", 0) / 1e6,
                            "prompt_eval_duration_ms": data.get("prompt_eval_duration", 0) / 1e6,
                            "eval_duration_ms": data.get("eval_duration", 0) / 1e6,
                            "prompt_eval_count": data.get("prompt_eval_count", 0),
                            "eval_count": data.get("eval_count", 0),
                        }
                        yield StreamChunk(content=delta, done=True, metadata=metadata)
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Ollama server: {str(e)}")
            raise OllamaUnavailableError(
                f"Could not connect to Ollama server at {self.base_url}. "
                "Ensure Ollama is running and server is healthy."
            ) from e
        except (OllamaUnavailableError, ProviderExecutionError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Ollama streaming chat completion: {str(e)}")
            raise ProviderExecutionError(f"Ollama streaming chat completion failed: {str(e)}") from e

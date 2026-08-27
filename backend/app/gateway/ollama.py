import json
import logging
import httpx
from app.gateway.base import ModelGateway
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.gateway.exceptions import OllamaUnavailableError, ProviderExecutionError

logger = logging.getLogger("sovereignx")

class OllamaGateway(ModelGateway):
    def __init__(self, base_url: str, model_name: str):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name or "qwen2.5:7b"

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
                "temperature": 0.0
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

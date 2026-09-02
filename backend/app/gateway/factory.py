import logging
from app.config import settings
from app.gateway.base import ModelGateway
from app.gateway.mock import MockGateway
from app.gateway.ollama import OllamaGateway
from app.gateway.exceptions import UnsupportedProviderError

logger = logging.getLogger("sovereignx")

def get_gateway() -> ModelGateway:
    """
    Factory function to retrieve the configured ModelGateway instance.
    """
    provider = settings.MODEL_PROVIDER.lower()
    logger.info(f"Initializing Model Gateway with provider: {provider}")
    
    if provider == "mock":
        return MockGateway()
    elif provider == "ollama":
        return OllamaGateway(
            base_url=settings.OLLAMA_BASE_URL,
            model_name=settings.MODEL_NAME,
            keep_alive=settings.OLLAMA_KEEP_ALIVE,
            think=settings.OLLAMA_THINK,
        )
    else:
        raise UnsupportedProviderError(f"Unsupported model provider: {settings.MODEL_PROVIDER}")

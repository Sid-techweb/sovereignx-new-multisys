from abc import ABC, abstractmethod
from app.schemas.analysis import AnalysisRequest, AnalysisResponse

class ModelGateway(ABC):
    @abstractmethod
    async def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        """
        Sends the analysis request to the configured model provider and
        returns a structured AnalysisResponse.
        
        Args:
            request: The AnalysisRequest object.
            
        Returns:
            The validated AnalysisResponse object.
            
        Raises:
            OllamaUnavailableError, ProviderInitializationError, ProviderExecutionError
        """
        pass

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        """
        Sends the text prompt to the configured model provider and
        returns the raw generated text response.
        
        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt to ground the generation context.
            
        Returns:
            The raw text response string.
            
        Raises:
            OllamaUnavailableError, ProviderExecutionError
        """
        pass


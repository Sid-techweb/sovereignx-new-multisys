from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Optional, AsyncGenerator
from app.schemas.analysis import AnalysisRequest, AnalysisResponse


@dataclass
class StreamChunk:
    """
    One increment of a streamed chat completion.

    `content` is the incremental text delta for this chunk (empty on the
    final chunk unless the provider's last token arrives alongside `done`).
    `metadata` is populated only on the final chunk (done=True) with the
    provider's own timing/token-count fields, converted to milliseconds
    where applicable, so streaming does not lose latency diagnosability.
    """
    content: str
    done: bool
    metadata: Optional[Dict] = None


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

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        options: Optional[Dict] = None
    ) -> str:
        """
        Sends a multi-turn conversation (list of {"role", "content"} messages,
        role one of "system"/"user"/"assistant") to the configured model
        provider and returns the raw generated reply text.

        This is the shared entry point for both general conversational chat
        and RAG-augmented chat: callers assemble the message list (system
        prompt + optional retrieved context + recent history + current user
        message) and this method performs a single generation call.

        Args:
            messages: Ordered list of chat messages.
            options: Optional provider-specific generation options
                (e.g. temperature, num_predict).

        Returns:
            The raw text response string.

        Raises:
            OllamaUnavailableError, ProviderExecutionError
        """
        pass

    @abstractmethod
    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        options: Optional[Dict] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Streaming counterpart to chat_completion(): same inputs, but yields
        StreamChunk increments as the provider generates them instead of
        waiting for the full response. The final yielded chunk has
        done=True and carries the provider's timing/token-count metadata.

        Existing chat_completion() callers are unaffected -- this is an
        additive capability, not a replacement.

        Args:
            messages: Ordered list of chat messages.
            options: Optional provider-specific generation options.

        Yields:
            StreamChunk instances; the last one has done=True.

        Raises:
            OllamaUnavailableError, ProviderExecutionError
        """
        pass
        yield  # pragma: no cover -- makes this an async generator for the ABC signature


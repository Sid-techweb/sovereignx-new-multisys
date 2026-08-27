class GatewayError(Exception):
    """Base exception for Model Gateway errors."""
    pass

class UnsupportedProviderError(GatewayError):
    """Raised when the configured provider is not supported."""
    pass

class OllamaUnavailableError(GatewayError):
    """Raised when the Ollama server is offline or unreachable."""
    pass

class ProviderInitializationError(GatewayError):
    """Raised when a gateway provider fails to initialize."""
    pass

class ProviderExecutionError(GatewayError):
    """Raised when a gateway provider execution fails."""
    pass

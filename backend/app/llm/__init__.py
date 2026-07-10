"""LLM abstraction layer (M0).

Unifies multiple LLM providers under LangChain's BaseChatModel interface.
Only three APIs are exposed:
  - get_chat_model(): factory returning a BaseChatModel for the current config
  - list_available_providers(): enumerate all providers and their config status
  - test_connectivity(): for health checks, makes a minimal request to the current provider

Business code uses:
    from app.llm import get_chat_model
    llm = get_chat_model()
"""

from app.llm.provider import (
    PROVIDER_REGISTRY,
    ProviderConfig,
    get_chat_model,
    list_available_providers,
    test_connectivity,
)

__all__ = [
    "PROVIDER_REGISTRY",
    "ProviderConfig",
    "get_chat_model",
    "list_available_providers",
    "test_connectivity",
]

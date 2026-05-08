"""LLM 抽象层（M0）。

把多种 LLM provider 统一到 LangChain 的 BaseChatModel 接口下。
对外只暴露三个 API：
  - get_chat_model(): 工厂函数，按当前配置返回 BaseChatModel
  - list_available_providers(): 枚举所有 provider 及配置状态
  - test_connectivity(): 健康检查用，对当前 provider 做最小请求

业务代码统一用：
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

"""LLM Provider Layer 팩토리.

사용법 (M3/M4의 Agent 코드에서):

    from app.core.llm import get_llm_provider, get_embedding_provider

    llm = get_llm_provider()          # LLM_PROVIDER env에 따라 mock|ollama|anthropic
    embedder = get_embedding_provider()  # EMBEDDING_PROVIDER env에 따라 mock|ollama

새 Provider 추가 절차 (예: OpenAI):
1. app/core/llm/openai_provider.py를 anthropic_provider.py 패턴으로 작성
2. 아래 레지스트리 분기에 등록
3. app/core/config.py에 필요한 설정(OPENAI_API_KEY 등) 추가
4. tests/core/test_llm_providers.py에 팩토리/에러 테스트 추가
"""
from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.llm.base import (
    CompletionRequest,
    CompletionResponse,
    EmbeddingProvider,
    ImagePart,
    LLMProvider,
    LLMProviderError,
    Message,
    TextPart,
)
from app.core.llm.mock_provider import MockEmbeddingProvider, MockLLMProvider

__all__ = [
    "CompletionRequest",
    "CompletionResponse",
    "EmbeddingProvider",
    "ImagePart",
    "LLMProvider",
    "LLMProviderError",
    "Message",
    "TextPart",
    "get_embedding_provider",
    "get_llm_provider",
]


def get_llm_provider(settings: Settings | None = None, *, vision: bool = False) -> LLMProvider:
    """LLM Provider를 반환한다.

    vision=True: 이미지 입력이 필요한 호출(M4 explainer)용. ollama는 텍스트 모델(OLLAMA_MODEL)과
    Vision 모델(OLLAMA_VISION_MODEL)이 분리되어 있어 이 플래그로 후자를 선택한다. mock·anthropic은
    한 모델이 텍스트+비전을 겸하므로 플래그가 no-op이다.
    """
    s = settings or get_settings()
    name = s.llm_provider.lower()
    if name == "mock":
        return MockLLMProvider()
    if name == "ollama":
        from app.core.llm.ollama_provider import OllamaLLMProvider

        model = s.ollama_vision_model if vision else s.ollama_model
        return OllamaLLMProvider(base_url=s.ollama_base_url, model=model)
    if name == "anthropic":
        from app.core.llm.anthropic_provider import AnthropicLLMProvider

        return AnthropicLLMProvider(api_key=s.anthropic_api_key, model=s.anthropic_model)
    if name == "openai":
        raise LLMProviderError(
            "OpenAI Provider는 아직 구현되지 않았습니다 (슬롯 예약 상태). "
            "app/core/llm/__init__.py docstring의 'Provider 추가 절차'를 따라 추가하세요."
        )
    raise LLMProviderError(f"알 수 없는 LLM_PROVIDER: {name!r} (mock | ollama | anthropic)")


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    s = settings or get_settings()
    name = s.embedding_provider.lower()
    if name == "mock":
        return MockEmbeddingProvider()
    if name == "ollama":
        from app.core.llm.ollama_provider import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider(
            base_url=s.ollama_base_url, model=s.ollama_embedding_model
        )
    if name == "anthropic":
        raise LLMProviderError(
            "Anthropic은 임베딩 API를 제공하지 않습니다. "
            "EMBEDDING_PROVIDER=mock 또는 ollama를 사용하세요 (LLM_PROVIDER와 별도 설정)."
        )
    raise LLMProviderError(f"알 수 없는 EMBEDDING_PROVIDER: {name!r} (mock | ollama)")

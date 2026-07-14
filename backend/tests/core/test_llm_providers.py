"""LLM Provider Layer 테스트.

전부 네트워크 없이 실행된다 (비용 가드레일 검증 포함):
- Mock: 결정론성 검증
- Ollama: httpx.MockTransport로 HTTP 계층 모의
- Anthropic: 키 없는 생성이 즉시 실패하는지만 검증 (실제 호출 없음)
- 팩토리: 환경변수(설정)에 따른 Provider 전환
"""
import math

import httpx
import pytest

from app.core.config import Settings
from app.core.llm import (
    CompletionRequest,
    ImagePart,
    LLMProviderError,
    Message,
    TextPart,
    get_embedding_provider,
    get_llm_provider,
)
from app.core.llm.mock_provider import MockEmbeddingProvider, MockLLMProvider
from app.core.llm.ollama_provider import OllamaEmbeddingProvider, OllamaLLMProvider


def _settings(**overrides) -> Settings:
    # .env 파일의 값이 끼어들지 않도록 명시적 kwargs로만 구성
    return Settings(_env_file=None, **overrides)


# --- Mock Provider -----------------------------------------------------------


def test_mock_complete_is_deterministic():
    provider = MockLLMProvider()
    request = CompletionRequest(messages=[Message.user_text("같은 입력")])
    first = provider.complete(request)
    second = provider.complete(request)
    assert first.text == second.text
    assert first.provider == "mock"
    assert first.model == "mock"


def test_mock_complete_canned_responses_in_order():
    provider = MockLLMProvider(canned_responses=["첫 번째", "두 번째"])
    request = CompletionRequest(messages=[Message.user_text("아무거나")])
    assert provider.complete(request).text == "첫 번째"
    assert provider.complete(request).text == "두 번째"
    assert "MOCK" in provider.complete(request).text  # 소진 후엔 기본 더미


def test_mock_complete_accepts_vision_input():
    provider = MockLLMProvider()
    request = CompletionRequest(
        messages=[
            Message(
                role="user",
                parts=[TextPart(text="이 그림을 설명해줘"), ImagePart(data=b"\x89PNG fake")],
            )
        ]
    )
    response = provider.complete(request)
    assert "이미지 1개" in response.text


def test_mock_embedding_deterministic_unit_vectors():
    provider = MockEmbeddingProvider()
    [a1], [a2] = provider.embed(["문단 A"]), provider.embed(["문단 A"])
    [b] = provider.embed(["문단 B"])
    assert len(a1) == provider.dimension == 768
    assert a1 == a2, "같은 텍스트는 항상 같은 벡터여야 함"
    assert a1 != b, "다른 텍스트는 다른 벡터여야 함"
    assert math.isclose(math.sqrt(sum(v * v for v in a1)), 1.0, rel_tol=1e-9)


# --- Ollama Provider (HTTP 모의) ----------------------------------------------


def _ollama_client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    )


def test_ollama_complete_parses_chat_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["json"] = request.read()
        return httpx.Response(
            200,
            json={"model": "llama3.2", "message": {"role": "assistant", "content": "안녕"}},
        )

    provider = OllamaLLMProvider(
        base_url="http://testserver", model="llama3.2", client=_ollama_client(handler)
    )
    response = provider.complete(
        CompletionRequest(messages=[Message.user_text("hi")], system="너는 조수다")
    )
    assert captured["path"] == "/api/chat"
    assert b'"system"' in captured["json"]  # system 메시지 전달 확인
    assert response.text == "안녕"
    assert response.provider == "ollama"


def test_ollama_embed_parses_embeddings():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    provider = OllamaEmbeddingProvider(
        base_url="http://testserver", model="nomic-embed-text",
        client=_ollama_client(handler),
    )
    assert provider.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]


def test_ollama_connect_error_gives_actionable_message():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider = OllamaLLMProvider(
        base_url="http://testserver", model="llama3.2", client=_ollama_client(handler)
    )
    with pytest.raises(LLMProviderError, match="ollama serve"):
        provider.complete(CompletionRequest(messages=[Message.user_text("hi")]))


# --- Anthropic Provider (호출 없이 가드레일만) -----------------------------------


def test_anthropic_without_key_fails_at_construction():
    from app.core.llm.anthropic_provider import AnthropicLLMProvider

    with pytest.raises(LLMProviderError, match="ANTHROPIC_API_KEY"):
        AnthropicLLMProvider(api_key="", model="claude-sonnet-5")


# --- 팩토리: 환경변수 스위칭 ----------------------------------------------------


def test_factory_default_is_mock():
    """비용 가드레일의 핵심: 무설정 기본값은 mock이어야 한다."""
    settings = _settings()
    assert settings.llm_provider == "mock"
    assert settings.embedding_provider == "mock"
    assert isinstance(get_llm_provider(settings), MockLLMProvider)
    assert isinstance(get_embedding_provider(settings), MockEmbeddingProvider)


def test_ollama_vision_uses_separate_model():
    """vision=True면 ollama는 OLLAMA_VISION_MODEL을, 아니면 OLLAMA_MODEL을 쓴다."""
    s = _settings(llm_provider="ollama", ollama_model="qwen2.5:7b",
                  ollama_vision_model="qwen2.5vl:3b")
    text_provider = get_llm_provider(s)
    vision_provider = get_llm_provider(s, vision=True)
    assert text_provider._model == "qwen2.5:7b"
    assert vision_provider._model == "qwen2.5vl:3b"


def test_mock_ignores_vision_flag():
    """mock은 한 모델이 텍스트+비전 겸용이라 vision 플래그가 no-op."""
    assert isinstance(get_llm_provider(_settings(), vision=True), MockLLMProvider)


def test_factory_switches_by_env_value():
    assert isinstance(
        get_llm_provider(_settings(llm_provider="ollama")), OllamaLLMProvider
    )
    assert isinstance(
        get_embedding_provider(_settings(embedding_provider="ollama")),
        OllamaEmbeddingProvider,
    )
    # anthropic은 키가 있어야 생성됨
    from app.core.llm.anthropic_provider import AnthropicLLMProvider

    provider = get_llm_provider(
        _settings(llm_provider="anthropic", anthropic_api_key="sk-test-dummy")
    )
    assert isinstance(provider, AnthropicLLMProvider)


def test_factory_anthropic_without_key_raises():
    with pytest.raises(LLMProviderError, match="ANTHROPIC_API_KEY"):
        get_llm_provider(_settings(llm_provider="anthropic", anthropic_api_key=""))


def test_factory_anthropic_embedding_not_supported():
    with pytest.raises(LLMProviderError, match="임베딩 API"):
        get_embedding_provider(_settings(embedding_provider="anthropic"))


def test_factory_openai_slot_reserved():
    with pytest.raises(LLMProviderError, match="아직 구현되지"):
        get_llm_provider(_settings(llm_provider="openai"))


def test_factory_unknown_provider_raises():
    with pytest.raises(LLMProviderError, match="알 수 없는"):
        get_llm_provider(_settings(llm_provider="gemini"))

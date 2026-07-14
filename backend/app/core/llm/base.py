"""LLM Provider Layer의 인터페이스와 공용 타입.

FigureMate는 특정 LLM에 종속되지 않는다. M3(매칭 검증)·M4(설명 생성)의 Agent들은
이 인터페이스만 사용하고, 실제 Provider는 환경변수로 선택된다:

    LLM_PROVIDER=mock | ollama | anthropic | openai(슬롯 예약)
    EMBEDDING_PROVIDER=mock | ollama

LLM/임베딩을 별도 인터페이스로 분리한 이유: Anthropic API는 임베딩 엔드포인트가
없으므로(Claude는 completion/vision 전용), 단일 인터페이스면 "환경변수만으로 Provider
전환" 약속이 Anthropic 선택 시 깨진다. 분리하면 LLM=anthropic + 임베딩=ollama 같은
조합이 가능하다.

비용 가드레일 (CLAUDE.md): 기본값은 mock이며 어떤 Provider도 import 시점에 네트워크를
사용하지 않는다. 유료 Provider(anthropic)는 생성 시점에 키를 검증해 즉시 실패한다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Literal


class LLMProviderError(Exception):
    """Provider 설정 오류 또는 호출 실패."""


@dataclass
class TextPart:
    text: str


@dataclass
class ImagePart:
    """이미지 입력 (M4 Vision용). 원본 바이트를 담고, base64 등 인코딩은
    각 Provider 내부에서 자기 API 규격에 맞게 처리한다."""

    data: bytes
    media_type: str = "image/png"


Part = TextPart | ImagePart


@dataclass
class Message:
    role: Literal["user", "assistant"]
    parts: list[Part]

    @classmethod
    def user_text(cls, text: str) -> "Message":
        return cls(role="user", parts=[TextPart(text=text)])


@dataclass
class CompletionRequest:
    messages: list[Message]
    system: str | None = None
    max_tokens: int = 1024
    temperature: float = 0.0


@dataclass
class CompletionResponse:
    text: str
    model: str      # 예: "mock", "llama3.2", "claude-sonnet-5"
    provider: str   # FigureExplanation.model_used 기록 시 f"{provider}:{model}" 권장


class LLMProvider(ABC):
    """텍스트/Vision completion Provider."""

    name: ClassVar[str]
    supports_vision: ClassVar[bool] = False

    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResponse: ...


class EmbeddingProvider(ABC):
    """임베딩 Provider (M3 의미 매칭용, pgvector에 저장).

    dimension은 pgvector 컬럼 차원과의 계약이다 — Provider를 바꾸면 차원이 달라질 수
    있으므로, M3에서 임베딩을 저장할 때 어떤 Provider/차원으로 만들었는지 함께 기록할 것.
    """

    name: ClassVar[str]
    dimension: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

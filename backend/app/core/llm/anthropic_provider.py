"""AnthropicProvider — Optional Provider. Claude API를 사용한다 (유료, 키 필수).

비용 가드레일 (CLAUDE.md):
- 이 Provider는 LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY 설정이 모두 있어야 생성된다.
  키가 없으면 생성 시점에 즉시 명확한 에러를 던진다 (조용한 호출 실패 없음).
- 기본 Provider가 아니다 — .env 무설정 상태에서는 절대 이 코드가 실행되지 않는다.

Anthropic은 임베딩 API를 제공하지 않으므로 EmbeddingProvider 구현이 없다.
임베딩은 EMBEDDING_PROVIDER=mock|ollama를 사용할 것 (base.py 참고).
"""
from __future__ import annotations

import base64
from typing import ClassVar

from app.core.llm.base import (
    CompletionRequest,
    CompletionResponse,
    ImagePart,
    LLMProvider,
    LLMProviderError,
    TextPart,
)


class AnthropicLLMProvider(LLMProvider):
    name: ClassVar[str] = "anthropic"
    supports_vision: ClassVar[bool] = True

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise LLMProviderError(
                "LLM_PROVIDER=anthropic이지만 ANTHROPIC_API_KEY가 비어 있습니다. "
                ".env에 키를 설정하거나, 비용 없는 개발에는 LLM_PROVIDER=mock 또는 "
                "ollama를 사용하세요 (CLAUDE.md 비용 가드레일)."
            )
        from anthropic import Anthropic  # 지연 import — mock/ollama 사용 시 SDK 미로드

        self._client = Anthropic(api_key=api_key)
        self._model = model

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        messages = []
        for message in request.messages:
            content: list[dict] = []
            for part in message.parts:
                if isinstance(part, TextPart):
                    content.append({"type": "text", "text": part.text})
                elif isinstance(part, ImagePart):
                    content.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": part.media_type,
                                "data": base64.b64encode(part.data).decode(),
                            },
                        }
                    )
            messages.append({"role": message.role, "content": content})

        kwargs: dict = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if request.system:
            kwargs["system"] = request.system

        try:
            response = self._client.messages.create(**kwargs)
        except Exception as exc:  # anthropic SDK 예외를 공용 예외로 변환
            raise LLMProviderError(f"Anthropic 호출 실패: {exc}") from exc

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return CompletionResponse(text=text, model=response.model, provider=self.name)

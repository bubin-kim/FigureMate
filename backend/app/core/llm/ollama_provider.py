"""OllamaProvider — 로컬 Ollama 서버를 사용하는 무비용 Provider.

전제: `ollama serve`가 OLLAMA_BASE_URL(기본 http://localhost:11434)에서 실행 중이고
필요한 모델이 pull되어 있어야 한다 (예: `ollama pull llama3.2`,
`ollama pull nomic-embed-text`). 서버가 없으면 명확한 안내와 함께 실패한다.

네트워크는 localhost뿐이며 API 비용은 발생하지 않는다.
"""
from __future__ import annotations

import base64
from typing import ClassVar

import httpx

from app.core.llm.base import (
    CompletionRequest,
    CompletionResponse,
    EmbeddingProvider,
    ImagePart,
    LLMProvider,
    LLMProviderError,
    TextPart,
)

_CONNECT_HINT = (
    "Ollama 서버에 연결할 수 없습니다. `ollama serve`가 실행 중인지, "
    "OLLAMA_BASE_URL이 올바른지 확인하세요."
)


class OllamaLLMProvider(LLMProvider):
    name: ClassVar[str] = "ollama"
    supports_vision: ClassVar[bool] = True  # llava 등 비전 모델 사용 시

    def __init__(self, base_url: str, model: str, client: httpx.Client | None = None):
        self._model = model
        # client 주입은 테스트용 (httpx.MockTransport) — 실 네트워크 없이 검증 가능
        self._client = client or httpx.Client(base_url=base_url, timeout=120.0)

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        for message in request.messages:
            texts = [p.text for p in message.parts if isinstance(p, TextPart)]
            images = [
                base64.b64encode(p.data).decode()
                for p in message.parts
                if isinstance(p, ImagePart)
            ]
            entry: dict = {"role": message.role, "content": "\n".join(texts)}
            if images:
                entry["images"] = images
            messages.append(entry)

        try:
            response = self._client.post(
                "/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": request.temperature,
                        "num_predict": request.max_tokens,
                    },
                },
            )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise LLMProviderError(_CONNECT_HINT) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(f"Ollama 호출 실패: {exc.response.text[:200]}") from exc

        data = response.json()
        return CompletionResponse(
            text=data["message"]["content"],
            model=data.get("model", self._model),
            provider=self.name,
        )


class OllamaEmbeddingProvider(EmbeddingProvider):
    name: ClassVar[str] = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        dimension: int = 768,  # nomic-embed-text 기준. 모델 변경 시 함께 조정할 것
        client: httpx.Client | None = None,
    ):
        self._model = model
        self.dimension = dimension
        self._client = client or httpx.Client(base_url=base_url, timeout=120.0)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.post(
                "/api/embed", json={"model": self._model, "input": texts}
            )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise LLMProviderError(_CONNECT_HINT) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(f"Ollama 임베딩 실패: {exc.response.text[:200]}") from exc
        return response.json()["embeddings"]

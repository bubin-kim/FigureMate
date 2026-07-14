"""MockProvider — 기본 Provider. 실제 API를 호출하지 않고 개발용 더미 데이터를 반환한다.

결정론적으로 동작한다 (같은 입력 → 항상 같은 출력):
- complete: 입력 텍스트의 해시를 포함한 더미 텍스트. 테스트에서는 canned_responses로
  원하는 응답을 순서대로 주입할 수 있다.
- embed: 입력 텍스트를 시드로 한 고정 차원(768) 단위 벡터 — 같은 텍스트는 항상 같은
  벡터이므로 M3 골든 테스트가 가능하고, 다른 텍스트는 (해시 특성상) 다른 벡터가 된다.
"""
from __future__ import annotations

import hashlib
import math
import struct
from typing import ClassVar

from app.core.llm.base import (
    CompletionRequest,
    CompletionResponse,
    EmbeddingProvider,
    LLMProvider,
    TextPart,
)


class MockLLMProvider(LLMProvider):
    name: ClassVar[str] = "mock"
    supports_vision: ClassVar[bool] = True  # ImagePart를 받아도 에러 없이 동작

    def __init__(self, canned_responses: list[str] | None = None):
        self._canned = list(canned_responses or [])

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        if self._canned:
            text = self._canned.pop(0)
        else:
            joined = "\n".join(
                part.text
                for message in request.messages
                for part in message.parts
                if isinstance(part, TextPart)
            )
            image_count = sum(
                1
                for message in request.messages
                for part in message.parts
                if not isinstance(part, TextPart)
            )
            digest = hashlib.sha256(joined.encode()).hexdigest()[:8]
            marker = (
                f"[MOCK:{digest}] 개발용 더미 응답입니다 "
                f"(텍스트 {len(joined)}자, 이미지 {image_count}개 수신)."
            )
            # 유효한 JSON으로 응답한다 — 각 Agent의 파서가 구조 검증을 계속할 수 있게
            # (grounding 검증은 is_relevant=false로 불활성, explainer는 parse_ok=True로
            # none_found 설명을 저장). 2026-07-14: "파싱 실패=failed" 정책 도입에 맞춘 조정.
            import json as _json

            text = _json.dumps(
                {
                    "is_relevant": False,
                    "reason": "",
                    "summary": marker,
                    "detailed_explanation": marker,
                    "components": [],
                    "grounding": [],
                },
                ensure_ascii=False,
            )
        return CompletionResponse(text=text, model="mock", provider=self.name)


class MockEmbeddingProvider(EmbeddingProvider):
    name: ClassVar[str] = "mock"

    def __init__(self, dimension: int = 768):
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        # shake_256으로 필요한 길이의 결정론적 바이트를 뽑아 [-1, 1] 실수로 변환 후 정규화
        raw = hashlib.shake_256(text.encode()).digest(self.dimension * 4)
        values = [
            struct.unpack("<i", raw[i : i + 4])[0] / 2**31
            for i in range(0, len(raw), 4)
        ]
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]

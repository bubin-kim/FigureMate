"""explainer_agent 입출력 스키마 (docs/adding-an-agent.md 절차 2).

계약: Figure 이미지 + 캡션 + M3의 매칭 근거 문단 + figure_type을 받아, 근거를 갖춘
FigureExplanation을 생성한다. 근거가 없으면(matches 비어 있으면) 지어내지 않고
GroundingRef.source="none_found"로 정직하게 남긴다.

출력의 FigureExplanation은 app/schemas/explanation.py를 그대로 쓴다 (DB 저장은 호출부 책임 —
Agent는 id/generated_at을 채우지 않고, 그 두 필드는 저장 계층이 발급한다).
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.schemas.explanation import (
    ExplanationComponent,
    FigureType,
    GroundingRef,
)


class MatchedParagraph(BaseModel):
    """M3 매칭 결과 — explainer의 근거 재료."""

    paragraph_id: UUID
    text: str
    match_type: str          # explicit_reference | semantic_similarity
    relevance_score: float


class ExplainInput(BaseModel):
    figure_id: UUID
    figure_number: str
    caption: str
    figure_type: FigureType
    image_bytes: bytes
    image_media_type: str = "image/png"
    matches: list[MatchedParagraph] = []  # 비어 있으면 none_found 케이스


class ExplainOutput(BaseModel):
    """FigureExplanation의 생성 부분 (id/generated_at 제외 — 저장 계층이 발급)."""

    figure_id: UUID
    figure_type: FigureType
    summary: str
    detailed_explanation: str
    components: list[ExplanationComponent] = []
    grounding: list[GroundingRef]
    model_used: str
    # 모델 응답 JSON 파싱 성공 여부 (DB 저장 안 함). ollama는 temp=0에서도 출력이
    # 실행마다 달라 파싱 실패가 확률적으로 발생한다 — 호출부(pipeline)가 이 플래그로
    # 재시도 여부를 판단한다 (2026-07-14 실측).
    parse_ok: bool = True

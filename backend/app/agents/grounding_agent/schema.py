"""grounding_agent 입출력 스키마 (docs/adding-an-agent.md 절차 2).

이 Agent의 계약: Figure 하나 + 후보 문단들을 받아, 그 Figure를 설명/참조하는
문단 매칭 목록을 반환한다. DB 개체(FigureTextMatch)와 달리 여기의 MatchResult는
id가 없다 — 레코드 발급은 저장 계층(호출부)의 책임이고 Agent는 판단만 한다.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.schemas.match import MatchType


class ParagraphInput(BaseModel):
    """매칭 후보 문단. id는 그대로 출력의 paragraph_id로 전달된다."""

    id: UUID
    text: str


class FigureInput(BaseModel):
    id: UUID
    figure_number: str          # "Figure 3" — 명시 참조 탐지의 키
    caption: str                # 의미 매칭(2단계)의 질의 텍스트
    extraction_confidence: float  # M2 산출 — relevance_score 상한에 반영 (M3.md 조건 #3)


class GroundingInput(BaseModel):
    figure: FigureInput
    paragraphs: list[ParagraphInput]


class MatchResult(BaseModel):
    figure_id: UUID
    paragraph_id: UUID
    match_type: MatchType
    relevance_score: float               # 0~1
    quote_span: tuple[int, int] | None = None  # explicit인 경우만


class GroundingOutput(BaseModel):
    figure_id: UUID
    matches: list[MatchResult]

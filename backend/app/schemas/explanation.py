"""FigureExplanation / ExplanationComponent / GroundingRef Pydantic 스키마 (M4 산출물).

정의는 docs/data-model.md를 단일 진실 원천으로 따른다. figure_type은 원래 스키마에 없었으나
프롬프트 분기·UI 표시에 필요해 M4에서 FigureExplanation에 추가했다(data-model.md 갱신 반영).

핵심 원칙 (data-model.md): grounding이 빈 리스트이고 source가 "none_found"인 설명은 숨기지
않고 정직하게 표시한다. 근거를 조작해 채우지 않는다. explainer_agent는 이 스키마로 그 원칙을
강제한다 — 근거 없는 Figure는 source="none_found" + note로 사실을 남긴다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

FigureType = Literal["architecture", "plot", "qualitative", "other"]
GroundingSource = Literal["paragraph", "caption", "none_found"]


class GroundingRef(BaseModel):
    paragraph_id: UUID | None = None   # 본문 근거 (source="paragraph"일 때)
    source: GroundingSource
    note: str | None = None            # "본문에 명시되지 않음, 일반 지식 사용" 등


class ExplanationComponent(BaseModel):
    label: str                         # 예: "Multi-Head Attention"
    role: str                          # 이 구성요소가 하는 일 (1문장)
    plain_explanation: str             # 쉬운 설명 (비유 포함 가능)
    grounding: list[GroundingRef] = []


class FigureExplanation(BaseModel):
    id: UUID
    figure_id: UUID
    figure_type: FigureType
    summary: str                       # 1~2문장 핵심 요약
    detailed_explanation: str          # 본문 형태의 상세 설명
    components: list[ExplanationComponent] = []  # 아키텍처형에 유용, 그 외 빈 리스트
    grounding: list[GroundingRef]      # 이 설명이 참조한 근거 (none_found여도 항목으로 남김)
    model_used: str                    # 예: "ollama:qwen2.5vl:3b", "mock"
    generated_at: datetime

    model_config = {"from_attributes": True}

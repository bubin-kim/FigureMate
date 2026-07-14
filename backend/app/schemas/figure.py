"""Figure Pydantic 스키마.

정의는 docs/data-model.md를 단일 진실 원천으로 따른다. 이 파일을 수정하면
docs/data-model.md도 함께 갱신할 것.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.explanation import FigureExplanation

FigureStatus = Literal["extracted", "matching", "explained", "failed"]


class Figure(BaseModel):
    id: UUID
    paper_id: UUID
    figure_number: str
    caption: str
    image_uri: str
    page: int
    bbox: list[float]
    extraction_confidence: float
    status: FigureStatus

    model_config = {"from_attributes": True}


class FigureDetail(Figure):
    """GET /papers/{id}/figures/{fid} 응답 — Figure + M4 설명(없으면 None)."""

    explanation: FigureExplanation | None = None

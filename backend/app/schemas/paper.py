"""Paper / Section / Paragraph Pydantic 스키마.

정의는 docs/data-model.md를 단일 진실 원천으로 따른다. 이 파일을 수정하면
docs/data-model.md도 함께 갱신할 것.

TODO(M1): 아래 스텁을 docs/data-model.md의 Paper / Section / Paragraph 정의에 맞춰
완성하세요. (uuid, datetime, Literal 등 필요한 typing/pydantic import 추가)
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

UploadStatus = Literal[
    "uploaded", "parsing", "extracting_figures", "matching", "explaining", "done", "failed"
]


class Paper(BaseModel):
    id: UUID
    title: str | None = None
    filename: str
    upload_status: UploadStatus
    page_count: int
    created_at: datetime
    error_message: str | None = None

    model_config = {"from_attributes": True}


class PaperListItem(Paper):
    """GET /papers 목록 응답용 — 홈 화면 히스토리에 필요한 figure 수를 함께 내려준다."""

    figure_count: int = 0


class Section(BaseModel):
    id: UUID
    paper_id: UUID
    title: str
    order: int
    page_start: int
    page_end: int

    model_config = {"from_attributes": True}


class Paragraph(BaseModel):
    id: UUID
    section_id: UUID
    paper_id: UUID
    text: str
    order: int
    page: int
    bbox: list[float] | None = None

    model_config = {"from_attributes": True}


class SectionWithParagraphs(Section):
    """GET /papers/{id}/sections 응답용 — 섹션 안에 문단을 중첩."""

    paragraphs: list[Paragraph] = []


# TODO(M1): ParsedDocument는 document_parser.parse_document()의 반환 타입.
# DB 모델이 아니라 서비스 레이어 내부 전송 객체이므로 여기 두거나
# services/document_parser.py에 직접 정의해도 무방합니다 — 팀 컨벤션에 맞게 결정하세요.
class ParsedDocument(BaseModel):
    page_count: int
    sections: list[SectionWithParagraphs]

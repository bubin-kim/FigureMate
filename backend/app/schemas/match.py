"""FigureTextMatch Pydantic 스키마.

정의는 docs/data-model.md를 단일 진실 원천으로 따른다. 이 파일을 수정하면
docs/data-model.md도 함께 갱신할 것.

match_type이 2종인 이유(M3 Step 0 실측 기록 참고): '암묵 참조(implicit_reference)'
카테고리는 검토 후 도입하지 않기로 결정됨 — 해당 성격의 문장이 샘플 전체에서 1건뿐이고
임베딩 유사도 1위로 잡혀 별도 카테고리의 검색력 기여가 없으며, 암묵성 판정이 LLM
의존적이라 결정론적 스키마 값이 될 수 없기 때문.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

MatchType = Literal["explicit_reference", "semantic_similarity"]


class FigureTextMatch(BaseModel):
    id: UUID
    figure_id: UUID
    paragraph_id: UUID
    match_type: MatchType
    # explicit_reference: 본문에 "Figure N" 형태로 직접 언급됨 (신뢰도 높음, score=1.0)
    # semantic_similarity: 임베딩 유사도 기반 후보 (LLM 검증 통과)
    relevance_score: float  # 0~1
    quote_span: tuple[int, int] | None = None  # paragraph.text 내 참조 위치 (explicit인 경우)

    model_config = {"from_attributes": True}


class FigureTextMatchRead(FigureTextMatch):
    """GET .../matches 응답용 — 근거 문단의 원문을 함께 싣는다 (M4가 이걸 citation 재료로 씀)."""

    paragraph_text: str
    paragraph_page: int

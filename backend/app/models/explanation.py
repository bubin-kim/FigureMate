"""FigureExplanation SQLAlchemy ORM 모델 (M4 산출물). docs/data-model.md 정의를 따른다.

설계 결정 (M4 Step 2):
- Figure 1개 = 설명 1개 (1:1). figure_id에 unique 인덱스.
- components / grounding은 중첩 구조이고 설명 단위로 통째로 읽히므로(M5가 한 번에 표시,
  개별 조회 안 함) 정규화 대신 JSONB로 저장한다. GroundingRef.paragraph_id는 JSON 안에서
  문자열 UUID로 보관 — FK 강제는 없지만, 실제 근거의 정본은 M3의 FigureTextMatch(FK 있음)이고
  여기 grounding은 그것을 가리키는 표시용 스냅샷이다.
- figure_type은 원래 스키마에 없던 필드 — 프롬프트 분기·UI 표시용으로 추가(data-model.md 갱신).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class FigureExplanation(Base):
    __tablename__ = "figure_explanations"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    figure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("figures.id", ondelete="CASCADE"), unique=True, index=True
    )
    figure_type: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detailed_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    components: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    grounding: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model_used: Mapped[str] = mapped_column(String, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    figure: Mapped["Figure"] = relationship(back_populates="explanation")  # noqa: F821

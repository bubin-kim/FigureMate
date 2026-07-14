"""FigureTextMatch SQLAlchemy ORM 모델. docs/data-model.md 정의를 따른다.

M1 paper.py 패턴 그대로 — UUID PK, 외래키 인덱스, cascade 삭제.
figure_id 인덱스: M4에서 Figure 단위로 근거 문단을 조회하는 것이 주 접근 패턴.
quote_span은 bbox와 같은 방식으로 int 배열로 저장 (tuple ↔ list 변환은 스키마 계층 책임).
"""
import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class FigureTextMatch(Base):
    __tablename__ = "figure_text_matches"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    figure_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("figures.id", ondelete="CASCADE"), index=True
    )
    paragraph_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paragraphs.id", ondelete="CASCADE"), index=True
    )
    match_type: Mapped[str] = mapped_column(String, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    quote_span: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)

    figure: Mapped["Figure"] = relationship(back_populates="matches")  # noqa: F821

"""Figure SQLAlchemy ORM 모델. docs/data-model.md의 Figure 정의를 따른다.

M1의 paper.py 패턴을 그대로 따름 — UUID PK, 외래키 인덱스, cascade 삭제.
paper_id 인덱스: M3에서 논문 단위 Figure 조회가 잦으므로 (paper.py의 Paragraph와 동일한 이유).
"""
import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, FLOAT, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Figure(Base):
    __tablename__ = "figures"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    figure_number: Mapped[str] = mapped_column(String, nullable=False)  # 예: "Figure 1", 실패 시 "Figure ?N"
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    image_uri: Mapped[str] = mapped_column(String, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[list[float]] = mapped_column(ARRAY(FLOAT), nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="extracted")

    paper: Mapped["Paper"] = relationship(back_populates="figures")  # noqa: F821
    matches: Mapped[list["FigureTextMatch"]] = relationship(  # noqa: F821
        back_populates="figure", cascade="all, delete-orphan"
    )
    explanation: Mapped["FigureExplanation | None"] = relationship(  # noqa: F821
        back_populates="figure", cascade="all, delete-orphan", uselist=False
    )

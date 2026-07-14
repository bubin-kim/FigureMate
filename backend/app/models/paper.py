"""Paper / Section / Paragraph SQLAlchemy ORM 모델.

TODO(M1): docs/data-model.md 정의에 맞춰 컬럼을 완성하세요.
- id 컬럼들은 UUID (server_default=text("gen_random_uuid()") 등 pgcrypto/uuid 확장 사용,
  또는 Python 측에서 uuid4() default)
- Paragraph.paper_id는 조회 편의를 위한 비정규화 컬럼 (section을 거치지 않고 바로 조회 가능하도록).
  Section을 통해서도 갈 수 있지만 M3 매칭 시 자주 조회되므로 직접 컬럼을 둔다.
- relationship()으로 Paper -> Section -> Paragraph 양방향 탐색 가능하게 구성.
- 생성 후 `alembic revision --autogenerate -m "create paper/section/paragraph"` 로
  마이그레이션 파일을 생성하고 review 후 alembic upgrade head 실행.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, FLOAT, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    upload_status: Mapped[str] = mapped_column(String, nullable=False, default="uploaded")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_uri: Mapped[str] = mapped_column(String, nullable=False)  # 원본 PDF 저장 경로
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sections: Mapped[list["Section"]] = relationship(back_populates="paper", cascade="all, delete-orphan")
    figures: Mapped[list["Figure"]] = relationship(  # noqa: F821
        back_populates="paper", cascade="all, delete-orphan"
    )


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)

    paper: Mapped["Paper"] = relationship(back_populates="sections")
    paragraphs: Mapped[list["Paragraph"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )


class Paragraph(Base):
    __tablename__ = "paragraphs"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sections.id", ondelete="CASCADE"), index=True
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    # bbox: [x0, y0, x1, y1] — 하이라이트 UI용, 파싱 단계에서 못 얻으면 NULL 허용
    bbox: Mapped[list[float] | None] = mapped_column(ARRAY(FLOAT), nullable=True)

    section: Mapped["Section"] = relationship(back_populates="paragraphs")

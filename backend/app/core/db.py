"""SQLAlchemy 엔진/세션 설정.

M1 작업지시서(docs/milestones/M1.md) Step 1~2 참고.
이후 마일스톤에서 모델이 늘어나도 이 파일은 거의 바뀌지 않아야 한다 — 새 모델은
app/models/ 아래에 추가하고 Base.metadata에 자동으로 포함되게 한다.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """모든 ORM 모델의 기반 클래스. app/models/*.py에서 이걸 상속한다."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends()로 주입할 DB 세션."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

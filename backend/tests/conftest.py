"""공통 pytest fixture.

- 테스트 DB: figuremate_test (TEST_DATABASE_URL 환경변수로 재정의 가능).
  세션 시작 시 테이블을 새로 만들고, 테스트마다 트랜잭션을 롤백해 서로 격리한다.
- client: FastAPI TestClient. get_db 의존성을 테스트 세션으로 교체하고,
  storage 경로를 tmp_path로 돌려 실제 ./storage를 오염시키지 않는다.

★ 테스트는 로컬 .env의 Provider 설정과 무관하게 **항상 mock**으로 돈다 (비용 0·결정론·
네트워크 없음). 아래 os.environ 설정을 app import보다 먼저 두어, get_settings()의 첫 호출이
mock을 읽게 강제한다 (os.environ이 .env 파일 값보다 우선). 이 강제가 없으면 개발자의
로컬 .env에 LLM_PROVIDER=ollama가 있을 때 테스트가 실제 ollama를 호출해 느려지고 깨진다.
"""
import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"

from pathlib import Path  # noqa: E402

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes_papers import get_paper_processor
from app.core.db import Base, get_db
from app.main import app
from app.services import storage
from app.services.pipeline import process_paper

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://figuremate:figuremate@localhost:5432/figuremate_test",
)


@pytest.fixture
def sample_pdf_dir():
    return Path(__file__).parent / "fixtures" / "sample_papers"


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    """테스트마다 외부 트랜잭션 안에서 동작하는 세션. 라우트가 commit해도
    (create_savepoint 모드 덕에) 테스트 종료 시 전부 롤백된다."""
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def client(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(storage.settings, "storage_local_path", str(tmp_path))

    def _override_get_db():
        yield db_session

    def _override_processor():
        # 백그라운드 처리기를 테스트 세션으로 동기 실행한다 (프로덕션은 자체 SessionLocal).
        # TestClient가 BackgroundTasks를 응답 직후 동기로 돌리므로, mock Provider(기본)에서는
        # 즉시 완료된다 — POST 응답엔 "parsing", 이후 GET엔 "done"이 보인다.
        def _process(paper_id):
            process_paper(paper_id, db_session)

        return _process

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_paper_processor] = _override_processor
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()

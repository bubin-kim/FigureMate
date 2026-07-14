"""논문 업로드 및 조회 API.

처리 정책 (M3에서 비동기로 전환 — docs/architecture.md 5절):
- POST /papers는 파일 저장 + Paper 레코드(upload_status="parsing") 생성 후 **즉시 응답**하고,
  parse→figure→matching 파이프라인은 백그라운드에서 실행한다. 매칭이 LLM 검증 때문에
  논문당 수 분 걸려 동기 처리가 불가능하기 때문(M1~M2의 동기 정책을 여기서 대체).
- 클라이언트는 GET /papers/{id}의 upload_status를 폴링해 진행/완료(done)/실패(failed)를 판단한다.
- 요청 자체가 잘못된 경우(비PDF·빈 파일)만 422로 즉시 거부한다.
- 백그라운드 처리기는 get_paper_processor 의존성으로 주입한다 (테스트에서 교체 가능).
"""
import uuid
from typing import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import SessionLocal, get_db
from app.models import Figure, Paper, Section
from app.schemas import paper as schemas
from app.services import storage
from app.services.pipeline import process_paper

router = APIRouter()


def get_paper_processor() -> Callable[[uuid.UUID], None]:
    """백그라운드 처리기를 반환한다. 자체 DB 세션을 열어 process_paper를 실행한다
    (요청 세션은 응답 후 닫히므로 재사용 불가). 테스트는 이 의존성을 override해
    테스트 세션으로 동기 실행한다."""

    def _process(paper_id: uuid.UUID) -> None:
        db = SessionLocal()
        try:
            process_paper(paper_id, db)
        finally:
            db.close()

    return _process


@router.post("", response_model=schemas.Paper)
async def upload_paper(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    processor: Callable[[uuid.UUID], None] = Depends(get_paper_processor),
) -> Paper:
    filename = file.filename or "unnamed.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="PDF 파일만 업로드할 수 있습니다.")
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=422, detail="빈 파일입니다.")

    storage_uri = storage.save_pdf(file_bytes, filename)
    paper = Paper(
        filename=filename,
        upload_status="parsing",
        page_count=0,
        storage_uri=storage_uri,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    background_tasks.add_task(processor, paper.id)
    return paper


@router.get("", response_model=list[schemas.PaperListItem])
async def list_papers(db: Session = Depends(get_db)) -> list[schemas.PaperListItem]:
    """업로드한 논문 히스토리 (최신순). 홈 화면의 '지난 논문 다시 보기' 목록용."""
    rows = db.execute(
        select(Paper, func.count(Figure.id))
        .outerjoin(Figure, Figure.paper_id == Paper.id)
        .group_by(Paper.id)
        # created_at은 트랜잭션 시작 시각(func.now())이라 동시 업로드 시 동률 가능 — id로 안정화
        .order_by(Paper.created_at.desc(), Paper.id.desc())
    ).all()
    return [
        schemas.PaperListItem(
            **schemas.Paper.model_validate(paper).model_dump(), figure_count=count
        )
        for paper, count in rows
    ]


def _get_paper_or_404(paper_id: uuid.UUID, db: Session) -> Paper:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="해당 논문을 찾을 수 없습니다.")
    return paper


@router.get("/{paper_id}", response_model=schemas.Paper)
async def get_paper(paper_id: uuid.UUID, db: Session = Depends(get_db)) -> Paper:
    return _get_paper_or_404(paper_id, db)


@router.get("/{paper_id}/sections", response_model=list[schemas.SectionWithParagraphs])
async def get_paper_sections(
    paper_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[Section]:
    _get_paper_or_404(paper_id, db)
    sections = db.scalars(
        select(Section)
        .where(Section.paper_id == paper_id)
        .options(selectinload(Section.paragraphs))
        .order_by(Section.order)
    ).all()
    for section in sections:
        section.paragraphs.sort(key=lambda p: p.order)
    return list(sections)

"""Figure 조회 API. docs/milestones/M2.md Step 4 참고.

Figure 추출 자체는 POST /papers 동기 흐름 안에서 수행된다 (routes_papers.py —
실측 최악 1.3초로 M1 동기 정책 유지, 사용자 결정. docs/architecture.md 참고).
여기는 조회 전용이다.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Figure, FigureTextMatch, Paper, Paragraph
from app.schemas import figure as schemas
from app.schemas import match as match_schemas
from app.services import storage

router = APIRouter()


def _get_paper_or_404(paper_id: uuid.UUID, db: Session) -> Paper:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="해당 논문을 찾을 수 없습니다.")
    return paper


@router.get("/{paper_id}/figures", response_model=list[schemas.Figure])
async def list_figures(paper_id: uuid.UUID, db: Session = Depends(get_db)) -> list[Figure]:
    _get_paper_or_404(paper_id, db)
    figures = db.scalars(
        select(Figure)
        .where(Figure.paper_id == paper_id)
        .order_by(Figure.page, Figure.figure_number)
    ).all()
    return list(figures)


@router.get("/{paper_id}/figures/{figure_id}", response_model=schemas.FigureDetail)
async def get_figure(
    paper_id: uuid.UUID, figure_id: uuid.UUID, db: Session = Depends(get_db)
) -> Figure:
    """Figure 상세 + M4 설명(있으면). 설명이 아직 없으면 explanation=null.
    (내부 호출자 get_figure_image/matches는 반환된 ORM 객체를 그대로 사용한다.)"""
    _get_paper_or_404(paper_id, db)
    figure = db.get(Figure, figure_id)
    if figure is None or figure.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="해당 Figure를 찾을 수 없습니다.")
    return figure


@router.get("/{paper_id}/figures/{figure_id}/image")
async def get_figure_image(
    paper_id: uuid.UUID, figure_id: uuid.UUID, db: Session = Depends(get_db)
) -> FileResponse:
    """크롭 이미지 파일 자체를 반환한다 (M5 뷰어에서 <img src>로 사용)."""
    figure = await get_figure(paper_id, figure_id, db)
    path = storage.get_file_path(figure.image_uri)
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지 파일이 존재하지 않습니다.")
    return FileResponse(path, media_type="image/png")


@router.get(
    "/{paper_id}/figures/{figure_id}/matches",
    response_model=list[match_schemas.FigureTextMatchRead],
)
async def get_figure_matches(
    paper_id: uuid.UUID, figure_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[match_schemas.FigureTextMatchRead]:
    """이 Figure에 매칭된 본문 문단 목록 (근거 문단 원문 포함, 관련도 내림차순).
    M3 산출물 — M4 설명 생성의 citation 재료다."""
    figure = await get_figure(paper_id, figure_id, db)
    rows = db.execute(
        select(FigureTextMatch, Paragraph)
        .join(Paragraph, FigureTextMatch.paragraph_id == Paragraph.id)
        .where(FigureTextMatch.figure_id == figure.id)
        .order_by(FigureTextMatch.relevance_score.desc())
    ).all()
    return [
        match_schemas.FigureTextMatchRead(
            id=m.id,
            figure_id=m.figure_id,
            paragraph_id=m.paragraph_id,
            match_type=m.match_type,
            relevance_score=m.relevance_score,
            quote_span=tuple(m.quote_span) if m.quote_span else None,
            paragraph_text=p.text,
            paragraph_page=p.page,
        )
        for m, p in rows
    ]

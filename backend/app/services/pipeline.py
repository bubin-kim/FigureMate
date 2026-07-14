"""논문 처리 파이프라인의 단계(stage) 함수들 (M3 Step 5 → M4 Step 6에서 재구성).

각 stage는 "순수 함수 호출 + DB 저장 + 상태 전이"를 담당하는 재사용 단위다. M4에서 이
함수들을 LangGraph 노드가 감싸며(app/graph/pipeline_graph.py), 진입점은 그래프의
run_pipeline이 된다. 이 파일을 삭제하지 않고 stage 함수로 유지하는 이유(M4.md Step 6 결정):
그래프 노드는 얇은 어댑터로 두고 실제 단계 로직은 여기서 재사용 — 로직을 그래프에 이식하지
않는다(M4.md "기존 로직을 그대로 노드로 감싸기만").

부분 실패 정책 (docs/architecture.md 5절):
- 파싱 실패 → failed (저장할 산출물 없음).
- Figure 추출 실패 → 섹션/문단 보존, 상태만 failed.
- 특정 Figure의 매칭/설명 실패 → 그 Figure만 건너뜀, 단계는 계속 진행.
- LLM 호출 실패(타임아웃 등) → 지수 백오프로 최대 3회 재시도 후 실패 처리
  (_retry_llm — M5 Step 6 E2E에서 실제 transient 실패가 관찰되어 구현).
"""
from __future__ import annotations

import logging
import re
import time
import uuid

logger = logging.getLogger(__name__)

_HANGUL_RE = re.compile(r"[가-힣]")
# 중국어 한자 + 키릴 혼입 (실측: siren→汽笛, "다иск리트傅里叶變換" — temp=0 불량 모드에서
# qwen2.5vl이 다국어 토큰을 섞음. 온도 상승으로 탈출)
_FOREIGN_RE = re.compile(r"[一-鿿Ѐ-ӿ]")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_PAREN_RE = re.compile(r"\([^()]*\)")  # 괄호구는 어미 판정에서 제외 ("…됩니다 (512 샘플).")
_TRAILING_NON_HANGUL_RE = re.compile(r"[^가-힣]+$")


def _looks_korean(text: str) -> bool:
    """설명이 한국어인지 러프하게 판정 (한글 10자 이상 — 기술 용어 영문 혼용 허용)."""
    return len(_HANGUL_RE.findall(text)) >= 10


def _polite_korean(text: str) -> bool:
    """모든 문장이 '~니다'(합쇼체)로 끝나는지 — Figure별 설명 톤 통일 게이트.

    표준을 합쇼체로 정한 이유(2026-07-14 실측): qwen2.5vl:7b는 특정 Figure에서 '-다'체
    지시를 3회 재시도 전부 무시할 만큼 합쇼체 성향이 강하다. 모델과 싸우면 재시도만
    소모하므로 모델 성향에 맞춰 표준을 정했다 (UI 문구도 존댓말이라 톤이 맞는다)."""
    total = 0
    for seg in _SENT_SPLIT_RE.split(text):
        seg = _TRAILING_NON_HANGUL_RE.sub("", _PAREN_RE.sub("", seg).strip())
        if not seg:
            continue
        total += 1
        if not seg.endswith("니다"):
            return False
    return total > 0


def _clean_style(text: str) -> bool:
    """설명 문체 게이트: 외국 문자(한자·키릴) 혼입 없음 + 합쇼체 통일 (prompt.md 문체 규칙)."""
    return not _FOREIGN_RE.search(text) and _polite_korean(text)

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.explainer_agent.node import explain_figure
from app.agents.explainer_agent.schema import ExplainInput, MatchedParagraph
from app.agents.grounding_agent.node import match_figure
from app.agents.grounding_agent.schema import (
    FigureInput,
    GroundingInput,
    ParagraphInput,
)
from app.core.llm import get_embedding_provider, get_llm_provider
from app.models import (
    Figure,
    FigureExplanation,
    FigureTextMatch,
    Paper,
    Paragraph,
    Section,
)
from app.services import storage
from app.services.document_parser import PDFParseError, parse_document
from app.services.figure_classifier import classify_figure
from app.services.figure_extractor import extract_figures


def _retry_llm(operation, *, attempts: int = 3, base_delay: float = 1.0, label: str = "LLM 호출"):
    """LLM 호출을 지수 백오프로 최대 attempts회 재시도한다 (architecture.md 5절 정책).

    범용 헬퍼 — 매칭 단계 등 향후 LLM 호출에 사용. explain 단계는 파싱 실패까지 함께
    다뤄야 해서 explain_stage_one의 통합 루프(전송+파싱 합산 3회)를 쓴다 — 이 헬퍼와
    중첩 사용 금지(재시도 곱셈으로 Figure당 최대 9회 호출이 났던 실측 사고, 2026-07-14).
    최종 실패 시 마지막 예외를 그대로 올린다 (호출부의 부분 실패 정책이 처리)."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < attempts - 1:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "%s 실패 (시도 %d/%d): %s — %.0f초 후 재시도",
                    label, attempt + 1, attempts, exc, delay,
                )
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def parse_stage(paper_id: uuid.UUID, db: Session) -> bool:
    """PDF 파싱 → 섹션/문단 저장. 성공하면 True, 실패하면 failed 표시 후 False."""
    paper = db.get(Paper, paper_id)
    paper.upload_status = "parsing"
    db.commit()
    try:
        parsed = parse_document(str(storage.get_pdf_path(paper.storage_uri)))
    except PDFParseError as exc:
        paper.upload_status = "failed"
        paper.error_message = str(exc)
        db.commit()
        return False
    paper.page_count = parsed.page_count
    for parsed_section in parsed.sections:
        section = Section(
            id=uuid.uuid4(),
            paper_id=paper.id,
            title=parsed_section.title,
            order=parsed_section.order,
            page_start=parsed_section.page_start,
            page_end=parsed_section.page_end,
        )
        db.add(section)
        for parsed_para in parsed_section.paragraphs:
            db.add(
                Paragraph(
                    id=uuid.uuid4(),
                    section_id=section.id,
                    paper_id=paper.id,
                    text=parsed_para.text,
                    order=parsed_para.order,
                    page=parsed_para.page,
                    bbox=parsed_para.bbox,
                )
            )
    paper.upload_status = "extracting_figures"
    db.commit()
    return True


def extract_stage(paper_id: uuid.UUID, db: Session) -> bool:
    """Figure 추출 → 저장. 성공하면 True, 실패하면 (섹션/문단 보존) failed 후 False."""
    paper = db.get(Paper, paper_id)
    try:
        extracted = extract_figures(str(storage.get_pdf_path(paper.storage_uri)))
    except Exception as exc:  # noqa: BLE001
        paper.upload_status = "failed"
        paper.error_message = f"Figure 추출 실패: {exc}"
        db.commit()
        return False
    for index, item in enumerate(extracted, start=1):
        image_uri = storage.save_figure_image(item.image_bytes, str(paper.id), index)
        db.add(
            Figure(
                id=uuid.uuid4(),
                paper_id=paper.id,
                figure_number=item.figure_number,
                caption=item.caption,
                image_uri=image_uri,
                page=item.page,
                bbox=item.bbox,
                extraction_confidence=item.extraction_confidence,
                status="extracted",
            )
        )
    paper.upload_status = "matching"
    db.commit()
    return True


def _ordered_paragraph_inputs(paper_id: uuid.UUID, db: Session) -> list[ParagraphInput]:
    """문서 등장 순서(섹션 order → 문단 order)의 문단 목록. match/explain 공통."""
    paragraphs = db.scalars(
        select(Paragraph)
        .join(Section, Paragraph.section_id == Section.id)
        .where(Paragraph.paper_id == paper_id)
        .order_by(Section.order, Paragraph.order)
    ).all()
    return [ParagraphInput(id=p.id, text=p.text) for p in paragraphs]


def match_stage(paper_id: uuid.UUID, db: Session) -> None:
    """저장된 Figure마다 grounding_agent로 매칭 → FigureTextMatch 저장."""
    para_inputs = _ordered_paragraph_inputs(paper_id, db)
    figures = db.scalars(select(Figure).where(Figure.paper_id == paper_id)).all()
    llm = get_llm_provider()
    embedder = get_embedding_provider()
    for figure in figures:
        try:
            output = match_figure(
                GroundingInput(
                    figure=FigureInput(
                        id=figure.id,
                        figure_number=figure.figure_number,
                        caption=figure.caption,
                        extraction_confidence=figure.extraction_confidence,
                    ),
                    paragraphs=para_inputs,
                ),
                llm=llm,
                embedder=embedder,
            )
        except Exception:  # noqa: BLE001 — 한 Figure 실패가 나머지를 막지 않음
            continue
        for match in output.matches:
            db.add(
                FigureTextMatch(
                    id=uuid.uuid4(),
                    figure_id=match.figure_id,
                    paragraph_id=match.paragraph_id,
                    match_type=match.match_type,
                    relevance_score=match.relevance_score,
                    quote_span=list(match.quote_span) if match.quote_span else None,
                )
            )
    db.commit()


def explain_stage_one(figure_id: uuid.UUID, db: Session) -> None:
    """Figure 하나에 대해 explainer_agent로 설명 생성 → FigureExplanation 저장.

    개별 Figure 단위라 LangGraph explain fan-out의 브랜치 본문이 된다. 실패는 그 Figure만
    status="failed"로 표시하고 예외를 삼킨다 (부분 실패 정책)."""
    figure = db.get(Figure, figure_id)
    if figure is None:
        return
    # 멱등성: 이미 설명이 있으면 건너뜀 — 서버 재시작으로 죽은 백그라운드 작업을
    # explain_stage 재실행으로 재개(resume)할 수 있게 한다 (figure_id unique 제약 보호).
    existing = db.scalar(
        select(FigureExplanation).where(FigureExplanation.figure_id == figure_id)
    )
    if existing is not None:
        return
    try:
        matches = db.scalars(
            select(FigureTextMatch)
            .where(FigureTextMatch.figure_id == figure_id)
            .order_by(FigureTextMatch.relevance_score.desc())
        ).all()
        matched = [
            MatchedParagraph(
                paragraph_id=m.paragraph_id,
                text=db.get(Paragraph, m.paragraph_id).text,
                match_type=m.match_type,
                relevance_score=m.relevance_score,
            )
            for m in matches
        ]
        figure_type = classify_figure(figure.caption)
        explain_input = ExplainInput(
            figure_id=figure.id,
            figure_number=figure.figure_number,
            caption=figure.caption,
            figure_type=figure_type,
            image_bytes=storage.get_file_path(figure.image_uri).read_bytes(),
            matches=matched,
        )
        # 통합 재시도 루프 — 총 3회 상한 (전송 실패든 파싱 실패든 시도 1회로 계산).
        # 처음에 전송 재시도(×3)와 파싱 재시도(×3)를 중첩했더니 Figure당 최대 9회
        # Vision 호출이 가능해져 한 Figure가 10분을 넘겼다(2026-07-14 실측) — 중첩 금지.
        # 재시도마다 temperature를 올린다(0.0→0.4→0.7): temp=0에서 특정 Figure가 일관되게
        # 깨진 JSON을 내는 불량 모드에 갇히는 사례를 실측으로 확인, 0.4에서 탈출함.
        # 품질 우선순위: 깨끗한 한국어(문체 통과) > 문체 미달 한국어 > 영어 > 없음(failed).
        output = None
        fallback = None  # 파싱은 됐지만 품질 미달(한자 혼입/영어) 후보 — 시도 소진 시 "없음"보다 낫다
        for attempt, temperature in enumerate((0.0, 0.4, 0.7)):
            try:
                candidate = explain_figure(explain_input, temperature=temperature)
            except Exception as exc:  # noqa: BLE001 — 전송 실패(타임아웃 등)
                logger.warning(
                    "%s 설명 생성 실패 (시도 %d/3, temp=%.1f): %s",
                    figure.figure_number, attempt + 1, temperature, exc,
                )
                time.sleep(2**attempt)
                continue
            if not candidate.parse_ok:
                logger.warning(
                    "%s 설명 JSON 파싱 실패 (시도 %d/3, temp=%.1f) — 재생성",
                    figure.figure_number, attempt + 1, temperature,
                )
                continue
            # 공백으로 잇는다 — 붙여 쓰면 summary의 마지막 문장이 문장 분리에서 다음 문장과
            # 합쳐져 어미 검사를 통과해버린다 (실측: 명사구 summary "…보여주는 그림."이 누락됨)
            body = f"{candidate.summary} {candidate.detailed_explanation}"
            full = " ".join(
                [body] + [c.label + c.role + c.plain_explanation for c in candidate.components]
            )
            if _looks_korean(body) and _clean_style(full):
                output = candidate
                break
            # 유효 JSON이지만 품질 미달(영어, 외국 문자 혼입, 합쇼체) — temp=0 불량 모드에서
            # 언어·문체 지시를 무시하는 사례 실측(2026-07-14). 최선 후보로 보관하고 온도를 올려 재시도.
            logger.warning(
                "%s 설명 품질 미달: %s (시도 %d/3, temp=%.1f) — 재생성",
                figure.figure_number,
                "문체 미달(외국 문자/합쇼체)" if _looks_korean(body) else "한국어 아님",
                attempt + 1, temperature,
            )
            if fallback is None or (
                _looks_korean(body)
                and not _looks_korean(fallback.summary + fallback.detailed_explanation)
            ):
                fallback = candidate
        if output is None and fallback is not None:
            logger.warning(
                "%s: 깨끗한 한국어 생성 실패 — 최선 후보라도 저장 (없음보다 낫다)",
                figure.figure_number,
            )
            output = fallback
        if output is None:
            # 3회 소진 — 깨진 원문을 저장하는 대신 정직하게 실패 처리 (UI: "설명이 없어요").
            logger.error("%s 설명 생성 최종 실패(전송/파싱) — failed 처리", figure.figure_number)
            figure.status = "failed"
            db.commit()
            return
    except Exception:  # noqa: BLE001
        # 재시도까지 소진한 실패 — 로그를 남기고 이 Figure만 실패 처리 (부분 실패 정책).
        logger.exception("%s 설명 생성 최종 실패 — 해당 Figure만 failed 처리", figure.figure_number)
        figure.status = "failed"
        db.commit()
        return
    db.add(
        FigureExplanation(
            id=uuid.uuid4(),
            figure_id=figure.id,
            figure_type=output.figure_type,
            summary=output.summary,
            detailed_explanation=output.detailed_explanation,
            components=[c.model_dump(mode="json") for c in output.components],
            grounding=[g.model_dump(mode="json") for g in output.grounding],
            model_used=output.model_used,
        )
    )
    figure.status = "explained"
    db.commit()


def figure_ids_for(paper_id: uuid.UUID, db: Session) -> list[uuid.UUID]:
    return list(
        db.scalars(select(Figure.id).where(Figure.paper_id == paper_id)).all()
    )


def explain_stage(paper_id: uuid.UUID, db: Session) -> None:
    """논문의 모든 Figure에 대해 설명을 생성한다 (Figure별 explain_stage_one 순차 호출).

    Figure별 처리는 explain_stage_one으로 분리되어 있어(개별 실패 격리), 향후 async +
    서버측 동시성 Provider로 전환 시 이 루프를 fan-out으로 바꿀 수 있다. sync/로컬 ollama
    에서는 순차가 병렬과 동등하므로(M4.md 한계 #3) 지금은 순차로 둔다.

    진입 시 paper 상태를 "explaining"으로 전이한다 — 이 단계가 논문당 수십 초~수 분이라
    폴링 UI(M5)가 현재 단계를 정확히 보여줄 수 있어야 하기 때문. 완료(done) 전이는
    finalize_stage가 담당한다."""
    paper = db.get(Paper, paper_id)
    paper.upload_status = "explaining"
    db.commit()
    for figure_id in figure_ids_for(paper_id, db):
        explain_stage_one(figure_id, db)


def finalize_stage(paper_id: uuid.UUID, db: Session) -> None:
    paper = db.get(Paper, paper_id)
    paper.upload_status = "done"
    db.commit()


def process_paper(paper_id: uuid.UUID, db: Session) -> None:
    """백그라운드 진입점 — LangGraph 그래프로 전체 파이프라인을 실행한다.

    (M4 Step 6: 순차 함수 호출을 LangGraph StateGraph로 재조립. 지연 import로 순환 참조 방지.)
    """
    from app.graph.pipeline_graph import run_pipeline

    run_pipeline(paper_id, db)

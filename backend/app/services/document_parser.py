"""PDF → 섹션/문단 구조화.

설계 원칙 (docs/architecture.md 2.1절):
- 결정론적 도구(PyMuPDF) 중심. LLM은 이번 마일스톤에서 사용하지 않는다.
- Paragraph.order는 논문 내 등장 순서를 반드시 유지해야 한다 (이후 grounding의 신뢰도 기반).
- 이 함수는 순수 함수로 유지한다 (DB 세션을 직접 다루지 않음) — 나중에 LangGraph 노드로
  감싸기 쉽도록. DB 저장은 호출부(API 라우트)에서 담당한다.

구현 방식 요약:
- 페이지별로 텍스트 블록/라인을 추출하고, 본문 폰트 크기(문자 수 가중 최빈값)를 기준으로
  "본문보다 크거나 볼드인 라인"을 헤딩 후보로 본다.
- 같은 블록 안에서 세로 구간이 겹치는 연속 라인은 하나의 "행(row)"으로 병합한다.
  (일부 PDF는 섹션 번호와 제목이 별도 라인으로 분리되어 있음 — 예: "1" + "Introduction")
- 헤딩 판별은 스타일(볼드/큰 폰트) + 텍스트 패턴(번호 매김 또는 관용적 헤딩 이름)을 모두
  요구한다. 번호 매김 패턴은 번호 뒤에 대문자로 시작하는 알파벳 제목이 따라와야 하므로,
  표 안의 볼드 숫자(예: "41.29")는 헤딩으로 오탐되지 않는다.
- 문단은 블록 단위로 만들되, 소문자로 시작하는 블록은 직전 문단의 연속(컬럼/페이지 넘어감)
  으로 보고 병합한다. 문장 단위로 쪼개지 않는다.

Front Matter 정책 (팀 결정, docs/architecture.md에도 기록):
- 첫 헤딩(보통 "Abstract") 이전의 텍스트(제목/저자/소속 등)는 "Front Matter"라는
  가상 섹션(order=0)으로 수집한다. 버리면 제목·저자 정보가 유실되고, 임의 섹션에 붙이면
  grounding이 오염되므로 명시적인 별도 섹션으로 둔다.

텍스트 정규화 정책 (원문 보존 우선, 최소한만):
- 라인 병합 시 공백 1개로 연결. 줄바꿈 하이픈("architec-" + "tures")만 제거.
- 그 외 문자 치환/소문자화 등은 하지 않는다 (Paragraph.text는 grounding 인용 원문).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import fitz


@dataclass
class ParsedParagraph:
    text: str
    order: int
    page: int
    bbox: list[float] | None = None


@dataclass
class ParsedSection:
    title: str
    order: int
    page_start: int
    page_end: int
    paragraphs: list[ParsedParagraph]


@dataclass
class ParsedDocument:
    page_count: int
    sections: list[ParsedSection]


class PDFParseError(Exception):
    """PDF 파싱이 근본적으로 불가능한 경우 (예: 이미지 스캔본, 손상된 파일)."""


# --- 내부 자료구조 ---------------------------------------------------------


@dataclass
class _Line:
    text: str
    bbox: tuple[float, float, float, float]
    max_size: float
    bold: bool


@dataclass
class _Row:
    """같은 세로 구간을 공유하는 라인들의 병합 결과 (섹션 번호 + 제목 분리 대응)."""

    lines: list[_Line] = field(default_factory=list)

    @property
    def text(self) -> str:
        parts = [ln.text for ln in sorted(self.lines, key=lambda l: l.bbox[0])]
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (
            min(ln.bbox[0] for ln in self.lines),
            min(ln.bbox[1] for ln in self.lines),
            max(ln.bbox[2] for ln in self.lines),
            max(ln.bbox[3] for ln in self.lines),
        )

    def all_styled(self, body_size: float) -> bool:
        return all(ln.bold or ln.max_size > body_size + 0.5 for ln in self.lines)


_BOLD_FLAG = 16  # PyMuPDF span flags의 bold 비트

# 번호 매김 헤딩: "1 Introduction", "3.2. Identity Mapping ..." 등.
# 번호 뒤에 대문자로 시작하고 알파벳이 2자 이상 이어지는 제목을 요구한다
# → 표 안의 볼드 숫자("41.29")나 숫자 나열("41.29 28.4")은 매칭되지 않는다.
_NUMBERED_HEADING = re.compile(r"^(\d{1,2}(\.\d{1,2})*)\.?\s+([A-Z][^\s]*(\s+\S+)*)$")

# 관용적 헤딩 (번호 없이 등장하는 경우): 행 전체가 정확히 이 단어(들)여야 한다.
_KEYWORD_HEADING = re.compile(
    r"^(Abstract|Introduction|Background|Related Works?|Methods?|Experiments?|Results?"
    r"|Discussion|Conclusions?|References|Bibliography|Acknowledg(e)?ments?"
    r"|Appendix(\s+[A-Z].*)?)$",
    re.IGNORECASE,
)

_PAGE_NUMBER = re.compile(r"^\d{1,4}$")
_ARXIV_WATERMARK = re.compile(r"^arXiv:\d{4}\.\d{4,5}")


def _extract_lines(page: fitz.Page) -> list[list[_Line]]:
    """페이지의 텍스트 블록별 라인 목록. 회전 텍스트(워터마크 등)는 제외."""
    blocks: list[list[_Line]] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        lines: list[_Line] = []
        for line in block.get("lines", []):
            if abs(line["dir"][0] - 1.0) > 0.01:  # 가로쓰기가 아닌 라인 제외
                continue
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text or _ARXIV_WATERMARK.match(text):
                continue
            lines.append(
                _Line(
                    text=text,
                    bbox=tuple(line["bbox"]),
                    max_size=max(round(span["size"], 1) for span in line["spans"]),
                    bold=any(span["flags"] & _BOLD_FLAG for span in line["spans"]),
                )
            )
        if lines:
            blocks.append(lines)
    return blocks


def _body_font_size(pages_blocks: list[list[list[_Line]]]) -> float:
    """본문 폰트 크기 추정: 문자 수 가중 최빈값."""
    sizes: Counter[float] = Counter()
    for blocks in pages_blocks:
        for lines in blocks:
            for ln in lines:
                sizes[ln.max_size] += len(ln.text)
    if not sizes:
        raise PDFParseError("PDF에서 텍스트를 전혀 추출하지 못했습니다 (스캔본 이미지 PDF일 수 있음).")
    return sizes.most_common(1)[0][0]


def _merge_rows(lines: list[_Line]) -> list[_Row]:
    """블록 내에서 세로 구간이 겹치는 연속 라인을 하나의 행으로 병합."""
    rows: list[_Row] = []
    for ln in lines:
        if rows:
            prev = rows[-1].bbox
            overlap = min(prev[3], ln.bbox[3]) - max(prev[1], ln.bbox[1])
            min_height = min(prev[3] - prev[1], ln.bbox[3] - ln.bbox[1])
            if min_height > 0 and overlap / min_height > 0.5:
                rows[-1].lines.append(ln)
                continue
        rows.append(_Row(lines=[ln]))
    return rows


def _is_heading(row: _Row, body_size: float) -> bool:
    text = row.text
    if len(text) > 120 or not row.all_styled(body_size):
        return False
    m = _NUMBERED_HEADING.match(text)
    if m and re.search(r"[A-Za-z]{2}", m.group(3)):
        return True
    return bool(_KEYWORD_HEADING.match(text))


def _join_fragments(parts: list[str]) -> str:
    """텍스트 조각을 공백으로 잇되, 줄바꿈 하이픈만 제거한다."""
    out = ""
    for part in parts:
        if not out:
            out = part
        elif out.endswith("-") and part[:1].islower():
            out = out[:-1] + part
        else:
            out = out + " " + part
    return out


def parse_document(pdf_path: str) -> ParsedDocument:
    """PDF를 섹션과 문단으로 구조화한다.

    반환값의 각 Paragraph는 이후 다른 마일스톤에서 grounding 참조 단위로 쓰이므로,
    text는 원문 그대로(불필요한 정규화 최소화), order는 논문 내 등장 순서를 유지해야 한다.

    Raises:
        PDFParseError: PDF를 열 수 없거나 텍스트를 전혀 추출하지 못한 경우
            (예: 스캔본 이미지 PDF — OCR은 이번 마일스톤 범위 밖).
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        raise PDFParseError(f"PDF를 열 수 없습니다: {exc}") from exc

    try:
        pages_blocks = [_extract_lines(page) for page in doc]
        page_count = doc.page_count
    finally:
        doc.close()

    body_size = _body_font_size(pages_blocks)

    sections: list[ParsedSection] = []

    def _start_section(title: str, page: int) -> ParsedSection:
        section = ParsedSection(
            title=title,
            order=len(sections),
            page_start=page,
            page_end=page,
            paragraphs=[],
        )
        sections.append(section)
        return section

    def _add_paragraph(section: ParsedSection, texts: list[str], page: int, bbox) -> None:
        text = _join_fragments(texts)
        if not text:
            return
        # 컬럼/페이지를 넘어 이어지는 문단: 소문자로 시작하면 직전 문단의 연속으로 병합
        if section.paragraphs and text[:1].islower():
            prev = section.paragraphs[-1]
            prev.text = _join_fragments([prev.text, text])
        else:
            section.paragraphs.append(
                ParsedParagraph(
                    text=text,
                    order=len(section.paragraphs),
                    page=page,
                    bbox=list(bbox) if bbox else None,
                )
            )
        section.page_end = max(section.page_end, page)

    current: ParsedSection | None = None
    for page_no, blocks in enumerate(pages_blocks, start=1):
        for lines in blocks:
            para_texts: list[str] = []
            para_bbox: tuple[float, float, float, float] | None = None
            for row in _merge_rows(lines):
                text = row.text
                if _PAGE_NUMBER.match(text) and not row.all_styled(body_size):
                    continue  # 페이지 번호
                if _is_heading(row, body_size):
                    if para_texts and current is not None:
                        _add_paragraph(current, para_texts, page_no, para_bbox)
                        para_texts, para_bbox = [], None
                    current = _start_section(text, page_no)
                    continue
                if current is None:
                    current = _start_section("Front Matter", page_no)
                para_texts.append(text)
                b = row.bbox
                para_bbox = (
                    b
                    if para_bbox is None
                    else (
                        min(para_bbox[0], b[0]),
                        min(para_bbox[1], b[1]),
                        max(para_bbox[2], b[2]),
                        max(para_bbox[3], b[3]),
                    )
                )
            if para_texts and current is not None:
                _add_paragraph(current, para_texts, page_no, para_bbox)

    if not any(s.paragraphs for s in sections):
        raise PDFParseError("PDF에서 텍스트를 전혀 추출하지 못했습니다 (스캔본 이미지 PDF일 수 있음).")

    return ParsedDocument(page_count=page_count, sections=sections)

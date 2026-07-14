"""PDF → Figure 이미지/캡션 추출.

M2 Step 2 구현. 전략은 Step 0 실측 후 사용자 승인을 받은 "캡션 앵커 파이프라인"이다
(docs/milestones/M2.md의 'Step 0 실측 후 전략 수정' 블록 참고):

1. 캡션 탐지가 Figure의 개수/정체성을 정의한다.
   - 패턴: 블록 시작이 "Figure N" 또는 "Fig. N" + 구두점(':' 또는 '.').
   - 구두점을 요구하는 이유(실측): "Table 2 summarizes...", "Fig. 6 (middle) shows..." 같은
     본문 문장이 구두점 없이 같은 접두 패턴으로 시작한다.
2. 캡션별로 위쪽 탐색 구역(zone)을 설정해 bbox를 결정한다.
   - 가로: 캡션이 속한 컬럼 폭 (2단 컬럼 페이지면 해당 컬럼, 아니면 본문 전체 폭).
   - 세로: 캡션 위로 올라가며 barrier(다른 Figure/Table 캡션, 본문 문단 블록,
     볼드 헤딩 라인)를 만날 때까지.
   - bbox = 구역 안의 (래스터 이미지 rect) ∪ (벡터 드로잉 클러스터) ∪ (구역 내 텍스트 라인).
     텍스트 라인을 포함하는 이유(실측): cluster_drawings()는 드로잉 경로만 잡아
     플롯의 축 라벨/눈금 텍스트가 빠진다.
3. 크롭 방식: 임베디드 래스터 이미지 1개가 bbox를 90% 이상 덮으면 원본 바이트를 직접
   추출(원본 해상도가 렌더링보다 높음 — 예: paper1 Fig 1은 1520x2239px), 그 외에는
   페이지를 200dpi로 렌더링해 bbox로 크롭. 실측 근거: 샘플 논문 12개 Figure 중 임베디드
   래스터는 3개뿐(paper1 Fig 1·2)이고 paper2는 7개 전부 벡터 그래픽이라 렌더링-크롭이
   주 경로다.

extraction_confidence 산정:
- 1.0: 단일 래스터 이미지가 bbox를 90% 이상 덮음 (가장 확실)
- 0.8: 벡터/래스터 그래픽 요소가 구역에서 발견됨
- 0.5: 그래픽 요소는 없지만 구역에 텍스트 라인이 있어 그것으로 bbox를 잡음
- 0.3: 구역이 비어 있어 "캡션 위 고정 높이(150pt)" 추정 크롭으로 후퇴 (최저 신뢰)

알려진 한계 (M2 완료 보고에 포함할 것):
- 캡션이 Figure '위'에 있는 레이아웃은 지원하지 않음 (두 샘플 논문 모두 캡션이 아래에 위치).
- 번호 없는 그림(장식 이미지 등)은 캡션이 없으므로 추출되지 않음 (M2.md의 방침대로
  번호 매김 의존을 기본 전략으로 함).

M1의 document_parser처럼 순수 함수를 유지한다 (DB/스토리지 접근 없음 — 저장은 호출부 책임).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import fitz

_CAPTION_RE = re.compile(r"^(Figure|Fig\.)\s+(\d+)\s*[.:]", re.IGNORECASE)
_TABLE_CAPTION_RE = re.compile(r"^Table\s+\d+\s*[.:]", re.IGNORECASE)

# 구두점 없는 캡션 스타일 지원 (2026-07-14, 사용자 승인 A+B):
# Springer 계열 논문은 "Fig. 5 A window of 2048 samples"처럼 번호 뒤 구두점이 없다.
# 단순 완화는 가짜 캡션 본문("Fig. 6 (middle) shows the behaviors...")을 다시 통과시키므로,
# 느슨한 매치는 두 조건을 함께 요구한다:
#   (A) 블록이 캡션답게 짧다 — 실측: 진짜 무구두점 캡션 31~109자 vs 가짜 캡션 본문 216자
#       → 150자 컷이 양쪽에 여유를 줌.
#   (B) 캡션 위 구역에 그래픽(래스터/벡터 클러스터)이 실제로 존재한다 — 본문 문장은 위에
#       body 문단이 붙어 있어 구역이 비므로 이 검증에서 걸러진다.
_CAPTION_LOOSE_RE = re.compile(r"^(Figure|Fig\.)\s+(\d+)\s+\S", re.IGNORECASE)
_LOOSE_CAPTION_MAX_CHARS = 150
_BOLD_FLAG = 16
_RENDER_DPI = 200
_FALLBACK_HEIGHT = 150.0  # 구역이 비었을 때 캡션 위로 가정하는 높이(pt)
_PAD = 3.0


@dataclass
class ExtractedFigure:
    figure_number: str          # "Figure 1" (캡션에서 파싱)
    caption: str                # 캡션 전문 (공백 정규화)
    page: int                   # 1-based
    bbox: list[float]           # [x0, y0, x1, y1] — 원본 PDF 좌표계
    image_bytes: bytes          # PNG
    extraction_confidence: float
    method: str                 # "embedded" | "render" | "render-fallback"


class FigureExtractionError(Exception):
    """PDF를 열 수 없는 등 추출이 근본적으로 불가능한 경우."""


@dataclass
class _Block:
    bbox: fitz.Rect
    lines: list[dict]
    text: str

    @property
    def line_count(self) -> int:
        return len(self.lines)


def _text_blocks(page: fitz.Page) -> list[_Block]:
    blocks = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        lines = b.get("lines", [])
        text = re.sub(
            r"\s+", " ",
            " ".join("".join(s["text"] for s in l["spans"]) for l in lines),
        ).strip()
        if text:
            blocks.append(_Block(bbox=fitz.Rect(b["bbox"]), lines=lines, text=text))
    return blocks


def _body_font_size(pages_blocks: list[list[_Block]]) -> float:
    sizes: Counter[float] = Counter()
    for blocks in pages_blocks:
        for block in blocks:
            for line in block.lines:
                for span in line["spans"]:
                    sizes[round(span["size"], 1)] += len(span["text"])
    return sizes.most_common(1)[0][0] if sizes else 10.0


def _block_mode_size(block: _Block) -> float:
    sizes: Counter[float] = Counter()
    for line in block.lines:
        for span in line["spans"]:
            sizes[round(span["size"], 1)] += len(span["text"])
    return sizes.most_common(1)[0][0]


def _is_all_bold(block: _Block) -> bool:
    spans = [s for l in block.lines for s in l["spans"] if s["text"].strip()]
    return bool(spans) and all(s["flags"] & _BOLD_FLAG for s in spans)


def _x_overlaps(a, b, min_ratio: float = 0.1) -> bool:
    overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
    return overlap > min_ratio * min(a.width, b.width)


def _x_inside(rect, zone, min_ratio: float = 0.6) -> bool:
    """rect의 가로 폭이 zone 가로 범위 안에 min_ratio 이상 들어있는가.
    전체 폭 텍스트(예: 논문 제목/저자 라인)가 한쪽 컬럼 구역의 내용물로
    끌려 들어오는 것을 막는다 (paper2 p1 실측에서 발견된 오염)."""
    if rect.width <= 0:
        return False
    overlap = min(rect.x1, zone.x1) - max(rect.x0, zone.x0)
    return overlap / rect.width >= min_ratio


def _is_two_column(blocks: list[_Block], text_area: fitz.Rect) -> bool:
    """페이지가 2단 컬럼인지: 좌/우 절반에 각각 좁은 블록이 2개 이상."""
    mid = (text_area.x0 + text_area.x1) / 2
    narrow = [b for b in blocks if b.bbox.width <= 0.55 * text_area.width]
    left = sum(1 for b in narrow if (b.bbox.x0 + b.bbox.x1) / 2 < mid)
    right = sum(1 for b in narrow if (b.bbox.x0 + b.bbox.x1) / 2 >= mid)
    return left >= 2 and right >= 2


def _is_barrier(block: _Block, zone_width: float, body_size: float) -> bool:
    """구역 확장을 멈추는 블록인가: 다른 캡션 / 본문 문단 / 볼드 헤딩 라인."""
    if _CAPTION_RE.match(block.text) or _TABLE_CAPTION_RE.match(block.text):
        return True
    # 본문 문단: 여러 줄 + 컬럼 폭에 가깝고 + 본문 폰트 크기
    if (
        block.line_count >= 2
        and block.bbox.width >= 0.5 * zone_width
        and abs(_block_mode_size(block) - body_size) <= 0.6
    ):
        return True
    # 볼드 헤딩 라인 (예: paper1 p13의 부록 헤딩 "Attention Visualizations")
    if (
        block.line_count == 1
        and _is_all_bold(block)
        and _block_mode_size(block) > body_size + 0.5
    ):
        return True
    return False


def extract_figures(pdf_path: str) -> list[ExtractedFigure]:
    """PDF에서 Figure 이미지와 캡션을 추출한다.

    반환되는 각 항목은 이미지 바이트, 캡션 텍스트, 페이지, bbox를 포함하며
    (실제 저장은 호출부에서 storage.py를 통해 처리), figure_number는 캡션에서 파싱한
    번호("Figure 1" 등)를 담는다. 캡션 앵커 방식이라 번호 파싱은 항상 성공하지만,
    스키마 계약(docs/data-model.md)대로 실패 시 "Figure ?N" 규약은 호출부에서 유지한다.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        raise FigureExtractionError(f"PDF를 열 수 없습니다: {exc}") from exc

    try:
        pages_blocks = [_text_blocks(page) for page in doc]
        body_size = _body_font_size(pages_blocks)
        figures: list[ExtractedFigure] = []

        for page_no, page in enumerate(doc, start=1):
            blocks = pages_blocks[page_no - 1]
            strict_captions = [b for b in blocks if _CAPTION_RE.match(b.text)]
            loose_candidates = [
                b for b in blocks
                if not _CAPTION_RE.match(b.text)
                and _CAPTION_LOOSE_RE.match(b.text)
                and len(b.text) <= _LOOSE_CAPTION_MAX_CHARS  # (A)
            ]
            if not strict_captions and not loose_candidates:
                continue

            text_area = fitz.Rect(
                min(b.bbox.x0 for b in blocks), min(b.bbox.y0 for b in blocks),
                max(b.bbox.x1 for b in blocks), max(b.bbox.y1 for b in blocks),
            )
            two_col = _is_two_column(blocks, text_area)
            image_rects = [
                (page.get_image_rects(img[0]), img[0])
                for img in page.get_images(full=True)
            ]
            raster = [(r, xref) for rects, xref in image_rects for r in rects]
            clusters = page.cluster_drawings()

            # (B) 무구두점 후보는 캡션 위 구역에 그래픽이 실제로 있어야 캡션으로 인정
            captions = strict_captions + [
                b for b in loose_candidates
                if _zone_has_graphics(b, blocks, raster, clusters, text_area, two_col, body_size)
            ]

            for caption in sorted(captions, key=lambda b: b.bbox.y0):
                figures.append(
                    _extract_one(
                        doc, page, page_no, caption, blocks, raster, clusters,
                        text_area, two_col, body_size,
                    )
                )
        return figures
    finally:
        doc.close()


def _compute_zone(caption, blocks, raster, clusters, text_area, two_col, body_size):
    """캡션 위 Figure 탐색 구역을 계산한다 (M2 승인 알고리즘 — 컬럼 폭 × barrier까지).

    반환: (zone, zone_hspan, innards). _extract_one과 무구두점 캡션 검증(B)이 공유한다."""
    # --- 가로 구역: 캡션이 속한 컬럼 폭 ---
    if two_col and caption.bbox.width <= 0.55 * text_area.width:
        mid = (text_area.x0 + text_area.x1) / 2
        caption_center = (caption.bbox.x0 + caption.bbox.x1) / 2
        zone_x0, zone_x1 = (text_area.x0, mid) if caption_center < mid else (mid, text_area.x1)
    else:
        zone_x0, zone_x1 = text_area.x0, text_area.x1
    zone_hspan = fitz.Rect(zone_x0, 0, zone_x1, 1)

    # --- 세로 구역: 캡션 위로 barrier까지 ---
    # 상단 한계는 텍스트+그래픽 통합 기준: 페이지 상단이 전부 이미지인 경우
    # (paper1 p3 — Figure 1 위에 텍스트가 전혀 없음) 텍스트만 보면 구역이 소멸한다.
    graphic_tops = [r.y0 for r, _ in raster] + [c.y0 for c in clusters]
    zone_top = min([text_area.y0, *graphic_tops])
    above = [
        b for b in blocks
        if b is not caption and b.bbox.y1 <= caption.bbox.y0 + 2 and _x_overlaps(b.bbox, zone_hspan)
    ]
    innards: list[_Block] = []
    for block in sorted(above, key=lambda b: b.bbox.y1, reverse=True):
        if _is_barrier(block, zone_x1 - zone_x0, body_size):
            zone_top = block.bbox.y1
            break
        innards.append(block)
    zone = fitz.Rect(zone_x0, zone_top, zone_x1, caption.bbox.y0)
    return zone, zone_hspan, innards


def _rect_in_zone(rect: fitz.Rect, zone: fitz.Rect, zone_hspan: fitz.Rect) -> bool:
    overlap_y = min(rect.y1, zone.y1) - max(rect.y0, zone.y0)
    return overlap_y > 0.5 * rect.height and _x_overlaps(rect, zone_hspan)


def _zone_has_graphics(caption, blocks, raster, clusters, text_area, two_col, body_size) -> bool:
    """(B) 검증: 이 블록을 캡션으로 봤을 때 위 구역에 그래픽이 실제로 존재하는가.
    본문 속 참조 문장("Fig. 6 (middle) shows...")은 바로 위가 body 문단(barrier)이라
    구역이 비어 False가 된다."""
    zone, zone_hspan, _ = _compute_zone(
        caption, blocks, raster, clusters, text_area, two_col, body_size
    )
    return any(_rect_in_zone(r, zone, zone_hspan) for r in clusters) or any(
        _rect_in_zone(r, zone, zone_hspan) for r, _ in raster
    )


def _caption_number(text: str) -> str:
    m = _CAPTION_RE.match(text) or _CAPTION_LOOSE_RE.match(text)
    return m.group(2)


def _extract_one(
    doc, page, page_no, caption, blocks, raster, clusters, text_area, two_col, body_size
) -> ExtractedFigure:
    figure_number = f"Figure {_caption_number(caption.text)}"

    zone, zone_hspan, innards = _compute_zone(
        caption, blocks, raster, clusters, text_area, two_col, body_size
    )
    zone_x0, zone_x1 = zone.x0, zone.x1

    def _in_zone(rect: fitz.Rect) -> bool:
        return _rect_in_zone(rect, zone, zone_hspan)

    graphic_rects = [r for r in clusters if _in_zone(r)]
    raster_in_zone = [(r, xref) for r, xref in raster if _in_zone(r)]
    graphic_rects += [r for r, _ in raster_in_zone]
    innard_rects = [
        b.bbox for b in innards if _in_zone(b.bbox) and _x_inside(b.bbox, zone)
    ]

    # --- bbox 확정 + 신뢰도 ---
    content = graphic_rects + innard_rects
    if graphic_rects:
        confidence, method = 0.8, "render"
    elif innard_rects:
        confidence, method = 0.5, "render"
    else:
        confidence, method = 0.3, "render-fallback"
        content = [fitz.Rect(zone_x0, max(zone.y0, caption.bbox.y0 - _FALLBACK_HEIGHT),
                             zone_x1, caption.bbox.y0)]

    bbox = fitz.Rect(
        min(r.x0 for r in content), min(r.y0 for r in content),
        max(r.x1 for r in content), max(r.y1 for r in content),
    )
    # zone이 의미적 경계다: 내용물(특히 회전 텍스트 라인)의 bbox가 zone을 넘어
    # 확장되면 barrier 위 헤딩이나 캡션 첫 줄이 크롭에 새어 들어온다 (육안 검증에서 발견).
    # 가로 패딩은 자유롭게, 세로 패딩은 zone 안쪽으로만 허용한다.
    bbox = bbox & zone
    bbox = fitz.Rect(
        bbox.x0 - _PAD,
        max(bbox.y0 - _PAD, zone.y0),
        bbox.x1 + _PAD,
        min(bbox.y1 + _PAD, zone.y1 - 0.5),
    ) & page.rect

    # --- 크롭: 단일 래스터가 bbox의 90% 이상을 덮으면 원본 바이트 ---
    image_bytes = None
    if len(raster_in_zone) == 1:
        rect, xref = raster_in_zone[0]
        if rect.get_area() >= 0.9 * bbox.get_area():
            pix = fitz.Pixmap(doc, xref)
            if pix.colorspace and pix.colorspace.n > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            image_bytes = pix.tobytes("png")
            confidence, method = 1.0, "embedded"
    if image_bytes is None:
        image_bytes = page.get_pixmap(clip=bbox, dpi=_RENDER_DPI).tobytes("png")

    return ExtractedFigure(
        figure_number=figure_number,
        caption=caption.text,
        page=page_no,
        bbox=[bbox.x0, bbox.y0, bbox.x1, bbox.y1],
        image_bytes=image_bytes,
        extraction_confidence=confidence,
        method=method,
    )

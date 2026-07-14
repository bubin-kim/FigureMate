"""figure_extractor.extract_figures()의 골든 케이스 + 네거티브 테스트.

docs/milestones/M2.md Step 5의 채점 기준:
- Figure 개수/캡션/페이지가 골든 케이스(<paper>.figures.expected.json)와 재현율 ≥90%로 일치
- 골든 외 추가 추출 Figure가 없어야 함 (있다면 오탐 판정 대상)
- 표(Table)가 Figure로 오탐되지 않음 — 골든의 known_non_figures 전 항목 검증
- 캡션 판별은 "Figure N" + 구두점을 요구 (가짜 캡션 본문 문장 거부)

conf 0.3 폴백(고정 높이 추정 크롭)은 두 샘플 논문에서 0건이라 실PDF로는 커버되지 않으므로
합성 PDF 테스트로 경로 자체가 정상 동작하는지 검증한다 (사용자 요청).
"""
import json

import fitz
import pytest

from app.services.figure_extractor import (
    _CAPTION_RE,
    FigureExtractionError,
    extract_figures,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _require(sample_pdf_dir, pdf_name):
    pdf_path = sample_pdf_dir / pdf_name
    expected_path = pdf_path.with_suffix("").with_suffix(".figures.expected.json") \
        if pdf_path.suffix == ".pdf" else None
    expected_path = sample_pdf_dir / (pdf_path.stem + ".figures.expected.json")
    if not pdf_path.exists():
        pytest.skip(f"샘플 PDF 없음: {pdf_path}")
    if not expected_path.exists():
        pytest.skip(f"Figure 골든 케이스 없음: {expected_path}")
    return pdf_path, json.loads(expected_path.read_text())


@pytest.mark.parametrize("pdf_name", ["paper1.pdf", "paper2.pdf"])
def test_extract_figures_matches_golden(sample_pdf_dir, pdf_name):
    pdf_path, expected = _require(sample_pdf_dir, pdf_name)
    result = extract_figures(str(pdf_path))

    # 1. 재현율 ≥ 90%: figure_number 일치 + 페이지 일치 + 캡션 부분 문자열 포함
    matched = 0
    for exp in expected["figures"]:
        found = [
            f for f in result
            if f.figure_number == exp["figure_number"]
            and f.page == exp["page"]
            and exp["caption_contains"].lower() in f.caption.lower()
        ]
        assert len(found) <= 1, f"{exp['figure_number']}이 중복 추출됨"
        matched += len(found)
    recall = matched / len(expected["figures"])
    assert recall >= 0.9, f"Figure 재현율 {recall:.2f} < 0.9"

    # 2. 골든 외 추가 추출 금지 (있다면 오탐 판정 절차가 필요하다는 신호)
    extra = [
        f.figure_number for f in result
        if not any(g["figure_number"] == f.figure_number for g in expected["figures"])
    ]
    assert extra == [], f"골든에 없는 추가 추출: {extra} — 오탐 여부 판정 필요"

    # 3. 각 Figure의 산출물 무결성: bbox 유효, confidence 범위, PNG 바이트
    for f in result:
        x0, y0, x1, y1 = f.bbox
        assert x1 > x0 and y1 > y0, f"{f.figure_number}: bbox가 비어 있음 {f.bbox}"
        assert 0 < f.extraction_confidence <= 1.0
        assert f.image_bytes.startswith(PNG_MAGIC), f"{f.figure_number}: PNG가 아님"


@pytest.mark.parametrize("pdf_name", ["paper1.pdf", "paper2.pdf"])
def test_known_non_figures_not_extracted(sample_pdf_dir, pdf_name):
    """골든의 known_non_figures(표 캡션 등) 전 항목이 Figure로 오탐되지 않아야 한다.
    M1 한계 #1(표 문제)과 연결된 M2 DoD 필수 네거티브 테스트."""
    pdf_path, expected = _require(sample_pdf_dir, pdf_name)
    result = extract_figures(str(pdf_path))
    for non_fig in expected.get("known_non_figures", []):
        offenders = [
            f.figure_number for f in result
            if f.caption.lower().startswith(non_fig["pattern"].lower())
        ]
        assert offenders == [], (
            f"{non_fig['pattern']}(p{non_fig['page']})이 Figure로 오탐됨: {offenders} "
            f"— {non_fig['why']}"
        )


def test_caption_regex_requires_punctuation():
    """캡션 판별 규칙(Step 0에서 사용자 승인): 'Figure N' 뒤 구두점(':' 또는 '.')이 필수.
    실측에서 발견된 가짜 캡션 본문 문장이 거부되는지 확인한다."""
    accepted = [
        "Figure 1: The Transformer - model architecture.",
        "Figure 2. Residual learning: a building block.",
        "Fig. 3: Something.",
        "figure 4. 대소문자 무관.",
    ]
    rejected = [
        "Table 2 summarizes our results and compares...",   # paper1 p8 실측
        "Fig. 6 (middle) shows the behaviors of ResNets.",  # paper2 p7 실측
        "Table 3 shows that all three options...",           # paper2 p6 실측
        "Figure 5 shows an example.",                        # 구두점 없는 본문 참조
        "Table 1. Architectures for ImageNet.",              # Table 캡션
    ]
    for text in accepted:
        assert _CAPTION_RE.match(text), f"캡션인데 거부됨: {text!r}"
    for text in rejected:
        assert not _CAPTION_RE.match(text), f"캡션이 아닌데 수용됨: {text!r}"


def test_fallback_fixed_height_crop_synthetic(tmp_path):
    """conf 0.3 폴백 경로 검증 (합성 PDF — 실논문 2편에서는 0건이라 별도 커버).
    캡션 위 구역에 그래픽도 텍스트도 없으면 고정 높이(150pt) 추정 크롭으로 후퇴하되,
    유효한 bbox와 PNG를 반환해야 한다."""
    doc = fitz.open()
    page = doc.new_page()
    body = (
        "This paragraph establishes the body font size and acts as the barrier "
        "block above the empty zone. It spans multiple lines so the extractor "
        "classifies it as a body paragraph rather than figure innards."
    )
    page.insert_textbox(fitz.Rect(72, 72, 540, 130), body, fontname="helv", fontsize=10)
    # 빈 구역(130~400) 아래에 캡션만 존재 — 그래픽/텍스트 없음
    page.insert_text((72, 410), "Figure 1: A caption with an empty zone above it.",
                     fontname="helv", fontsize=9)
    pdf_path = tmp_path / "fallback.pdf"
    doc.save(str(pdf_path))
    doc.close()

    result = extract_figures(str(pdf_path))
    assert len(result) == 1
    fig = result[0]
    assert fig.extraction_confidence == 0.3
    assert fig.method == "render-fallback"
    x0, y0, x1, y1 = fig.bbox
    assert y1 > y0 and x1 > x0
    # 고정 높이 150pt + 세로 패딩(위 3pt, 아래 캡션 직전 -0.5pt) = 최대 153.5pt
    assert (y1 - y0) <= 153.5, "폴백 크롭 높이는 고정 상한(150pt+패딩) 이내여야 함"
    assert fig.image_bytes.startswith(PNG_MAGIC)


def test_unpunctuated_caption_accepted_with_graphics_above(tmp_path):
    """무구두점 캡션 지원 (2026-07-14, A+B): 'Fig. N 텍스트' 스타일은
    (A) 150자 이하 + (B) 위에 그래픽 존재일 때만 캡션으로 인정한다.
    실사례: Springer 계열 논문의 'Fig. 5 A window of 2048 samples'."""
    doc = fitz.open()
    page = doc.new_page()
    body = ("This paragraph establishes the body font size for the page and acts "
            "as regular prose content above the figure area entirely.")
    page.insert_textbox(fitz.Rect(72, 72, 540, 110), body, fontname="helv", fontsize=10)
    # 그래픽 (사각형 드로잉 = 벡터 클러스터)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(150, 150, 400, 300))
    shape.finish(color=(0, 0, 0), width=1)
    shape.commit()
    # 무구두점 캡션 (그래픽 바로 아래)
    page.insert_text((150, 320), "Fig. 1 A window of 2048 samples", fontname="helv", fontsize=9)
    # 가짜 캡션 본문 문장 (위에 그래픽 없음 + 150자 초과): 캡션으로 인정되면 안 됨
    page.insert_textbox(
        fitz.Rect(72, 380, 540, 440),
        "Fig. 2 (middle) shows the behaviors of the networks. Also similar to the other "
        "cases, our models manage to overcome the optimization difficulty and demonstrate "
        "accuracy gains when the depth increases beyond one hundred layers overall.",
        fontname="helv", fontsize=10,
    )
    pdf_path = tmp_path / "loose_caption.pdf"
    doc.save(str(pdf_path))
    doc.close()

    result = extract_figures(str(pdf_path))
    numbers = [f.figure_number for f in result]
    assert "Figure 1" in numbers, "무구두점 진짜 캡션(그래픽 위에 존재)은 추출되어야 함"
    assert "Figure 2" not in numbers, "가짜 캡션 본문(길고 그래픽 없음)은 계속 거부되어야 함"


def test_corrupted_pdf_raises(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(FigureExtractionError):
        extract_figures(str(bad))

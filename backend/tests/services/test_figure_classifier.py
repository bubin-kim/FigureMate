"""figure_classifier 골든 테스트 (M4 Step 3).

두 샘플 논문 12개 Figure의 실제 캡션으로 타입 분류가 100% 맞는지 검증한다
(Vision 호출 없는 결정론적 휴리스틱이라 100%가 기준 — 미달이면 키워드 조정 필요).
"""
import pytest

from app.services.figure_classifier import classify_figure
from app.services.figure_extractor import extract_figures

# 사람이 이미지를 보고 정한 기대 타입 (Step 0 rubric 및 육안 확인 기반)
EXPECTED = {
    "paper1.pdf": {
        "Figure 1": "architecture", "Figure 2": "architecture",
        "Figure 3": "qualitative", "Figure 4": "qualitative", "Figure 5": "qualitative",
    },
    "paper2.pdf": {
        "Figure 1": "plot", "Figure 2": "architecture", "Figure 3": "architecture",
        "Figure 4": "plot", "Figure 5": "architecture", "Figure 6": "plot",
        "Figure 7": "plot",
    },
}


@pytest.mark.parametrize("pdf_name", ["paper1.pdf", "paper2.pdf"])
def test_classify_matches_expected_types(sample_pdf_dir, pdf_name):
    pdf_path = sample_pdf_dir / pdf_name
    if not pdf_path.exists():
        pytest.skip(f"샘플 PDF 없음: {pdf_path}")
    expected = EXPECTED[pdf_name]
    for figure in extract_figures(str(pdf_path)):
        got = classify_figure(figure.caption)
        assert got == expected[figure.figure_number], (
            f"{pdf_name} {figure.figure_number}: {got} (기대 {expected[figure.figure_number]}) "
            f"| {figure.caption[:60]}"
        )


def test_classify_priority_and_edge_cases():
    # 우선순위: plot이 architecture 단어보다 먼저 (Fig 7 "std of layer responses"는 plot)
    assert classify_figure("Figure 7. Standard deviations (std) of layer responses.") == "plot"
    # "Example network architectures" — 'example of'가 아니라 'example ' + architecture → architecture
    assert classify_figure("Figure 3. Example network architectures for ImageNet.") == "architecture"
    # 메커니즘 도해: architecture 명시어 없어도 'attention' 등으로 architecture
    assert classify_figure("Figure 2. Multi-Head Attention runs in parallel.") == "architecture"
    # 정성 예시: 'example of' → qualitative (architecture보다 먼저)
    assert classify_figure("Figure X. An example of the attention mechanism following deps.") == "qualitative"
    # 아무 키워드 없음 → other
    assert classify_figure("Figure 9. A photograph of the apparatus.") == "other"

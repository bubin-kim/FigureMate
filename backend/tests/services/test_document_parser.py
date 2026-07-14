"""document_parser.parse_document()의 골든 케이스 테스트.

docs/milestones/M1.md Step 5의 채점 기준:
- 섹션 탐지 재현율 90% 이상 (fuzzy match)
- Paragraph.order가 원문 순서와 일치 (역전 없음)
- 전체 문단 수가 0이 아니고 비정상적으로 많지 않음 (파싱이 깨지지 않았는지의 신호)

전제조건: tests/fixtures/sample_papers/ 아래에
- <paper>.pdf
- <paper>.expected.json  (형식은 해당 폴더 README.md 참고)

네거티브 테스트 (사용자 지시로 필수, Step 3에서 관찰된 오탐 위험 검증):
- paper1.pdf 본문 표의 볼드 숫자 셀("41.29", "28.4")이 섹션 헤딩으로 오탐되지 않아야 한다.
  합성 PDF 단위 테스트 + 골든 PDF 검증 두 가지로 확인한다.
"""
import difflib
import json
import re

import fitz
import pytest

from app.services.document_parser import PDFParseError, parse_document

_NUMERIC_ONLY = re.compile(r"^[\d\s.,%]+$")


def _normalize_title(title: str) -> str:
    """fuzzy match용 정규화: 리거처 복원, 소문자화, 영숫자 외 문자 정리."""
    title = title.replace("ﬁ", "fi").replace("ﬂ", "fl").lower()
    return re.sub(r"[^a-z0-9]+", " ", title).strip()


def _match_score(expected: str, actual: str) -> float:
    """정규화 완전 일치 > 부분 문자열 > 유사도 순으로 점수를 매긴다."""
    e, a = _normalize_title(expected), _normalize_title(actual)
    if e == a:
        return 1.0
    if e in a or a in e:
        return 0.9
    return difflib.SequenceMatcher(None, e, a).ratio()


def _match_sections(expected_sections, result_sections) -> dict:
    """기대 섹션마다 가장 점수 높은 결과 섹션을 1:1로 배정 (점수 0.8 미만은 미탐 처리).

    첫 매칭이 아니라 최고 점수를 쓰는 이유: '3.1. Residual Learning'이 유사도만으로
    '3. Deep Residual Learning'에 먼저 걸리는 오배정을 막기 위함."""
    matched = {}
    used = set()
    for exp in expected_sections:
        best_score, best_section = 0.0, None
        for section in result_sections:
            if id(section) in used:
                continue
            score = _match_score(exp["title"], section.title)
            if score > best_score:
                best_score, best_section = score, section
        if best_section is not None and best_score >= 0.8:
            matched[exp["title"]] = best_section
            used.add(id(best_section))
    return matched


def _load_expected(pdf_path):
    expected_path = pdf_path.with_suffix(".expected.json")
    if not expected_path.exists():
        pytest.skip(f"골든 케이스 없음: {expected_path} — M1 사전 준비물을 먼저 넣으세요.")
    return json.loads(expected_path.read_text())


def _require_pdf(sample_pdf_dir, pdf_name):
    pdf_path = sample_pdf_dir / pdf_name
    if not pdf_path.exists():
        pytest.skip(f"샘플 PDF 없음: {pdf_path} — M1 사전 준비물을 먼저 넣으세요.")
    return pdf_path


@pytest.mark.parametrize("pdf_name", ["paper1.pdf", "paper2.pdf"])
def test_parse_document_matches_golden(sample_pdf_dir, pdf_name):
    pdf_path = _require_pdf(sample_pdf_dir, pdf_name)
    expected = _load_expected(pdf_path)
    result = parse_document(str(pdf_path))

    # 1. 섹션 제목 재현율 >= 90% (fuzzy match)
    matched = _match_sections(expected["sections"], result.sections)
    recall = len(matched) / len(expected["sections"])
    missing = [e["title"] for e in expected["sections"] if e["title"] not in matched]
    assert recall >= 0.9, f"섹션 재현율 {recall:.2f} < 0.9, 미탐: {missing}"

    # 2. 매칭된 섹션의 최소 문단 수
    for exp in expected["sections"]:
        if exp["title"] in matched:
            section = matched[exp["title"]]
            assert len(section.paragraphs) >= exp["min_paragraphs"], (
                f"{exp['title']!r}: 문단 {len(section.paragraphs)}개 < "
                f"기대 최소 {exp['min_paragraphs']}개"
            )

    # 3. 순서 무결성: 섹션 order와 섹션 내 문단 order에 역전이 없어야 함
    assert [s.order for s in result.sections] == list(range(len(result.sections)))
    for section in result.sections:
        assert [p.order for p in section.paragraphs] == list(range(len(section.paragraphs))), (
            f"{section.title!r}의 문단 order가 연속 오름차순이 아님"
        )

    # 4. 전체 문단 수가 정상 범위 (파싱이 깨지지 않았는지의 신호)
    total_paragraphs = sum(len(s.paragraphs) for s in result.sections)
    assert 0 < total_paragraphs < 2000, f"문단 수 비정상: {total_paragraphs}"


def test_bold_table_numbers_in_golden_pdf_not_detected_as_sections(sample_pdf_dir):
    """paper1.pdf 본문 표에는 볼드 숫자 셀(예: '41.29', '28.4')이 실제로 존재한다.
    파싱 결과의 섹션 제목에 '숫자만으로 된 제목'이 하나도 없어야 한다."""
    pdf_path = _require_pdf(sample_pdf_dir, "paper1.pdf")
    result = parse_document(str(pdf_path))
    numeric_titles = [s.title for s in result.sections if _NUMERIC_ONLY.match(s.title)]
    assert numeric_titles == [], f"숫자만으로 된 섹션 제목이 오탐됨: {numeric_titles}"


def test_bold_numbers_not_headings_synthetic(tmp_path):
    """합성 PDF 단위 테스트: 볼드 숫자('41.29', '41.29 28.4')는 헤딩으로 잡히지 않고,
    진짜 헤딩('1 Introduction')만 섹션으로 잡혀야 한다."""
    doc = fitz.open()
    page = doc.new_page()
    body = (
        "This is ordinary body text used to establish the dominant font size. "
        "It repeats a few times so the size histogram clearly favors 10pt."
    )
    y = 80
    page.insert_text((72, y), "1 Introduction", fontname="hebo", fontsize=12)
    for i in range(4):
        y += 20
        page.insert_text((72, y), body, fontname="helv", fontsize=10)
    # 표를 흉내 낸 볼드 숫자 셀 (paper1의 BLEU 점수 표와 같은 상황)
    y += 30
    page.insert_text((72, y), "41.29", fontname="hebo", fontsize=10)
    y += 20
    page.insert_text((72, y), "41.29 28.4", fontname="hebo", fontsize=10)
    y += 30
    page.insert_text((72, y), "2 Background", fontname="hebo", fontsize=12)
    y += 20
    page.insert_text((72, y), body, fontname="helv", fontsize=10)
    pdf_path = tmp_path / "synthetic.pdf"
    doc.save(str(pdf_path))
    doc.close()

    result = parse_document(str(pdf_path))
    titles = [s.title for s in result.sections]

    assert any("Introduction" in t for t in titles), f"진짜 헤딩 미탐: {titles}"
    assert any("Background" in t for t in titles), f"진짜 헤딩 미탐: {titles}"
    numeric_titles = [t for t in titles if _NUMERIC_ONLY.match(t)]
    assert numeric_titles == [], f"볼드 숫자가 헤딩으로 오탐됨: {numeric_titles}"


def test_corrupted_pdf_raises_parse_error(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"this is not a pdf at all")
    with pytest.raises(PDFParseError):
        parse_document(str(bad))

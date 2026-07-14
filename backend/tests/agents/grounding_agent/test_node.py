"""grounding_agent 스캐폴드 단위 테스트 (docs/adding-an-agent.md 절차 7).

M3 Step 3 시점: 1단계(명시적 참조)의 골든 케이스. 2단계(의미 매칭)는 Step 4~6에서
실PDF 골든(paper{N}.matches.expected.json)과 함께 확장된다.
"""
import uuid

from app.agents.grounding_agent.node import (
    find_explicit_references,
    load_prompt,
    match_figure,
)
from app.agents.grounding_agent.schema import (
    FigureInput,
    GroundingInput,
    ParagraphInput,
)


def _make_input(figure_number: str, texts: list[str]) -> GroundingInput:
    return GroundingInput(
        figure=FigureInput(
            id=uuid.uuid4(),
            figure_number=figure_number,
            caption=f"{figure_number}: dummy caption.",
            extraction_confidence=0.8,
        ),
        paragraphs=[ParagraphInput(id=uuid.uuid4(), text=t) for t in texts],
    )


GOLDEN_TEXTS = [
    "Figure 1: The model architecture.",              # 캡션 자신 — 제외되어야 함
    "The encoder is shown in Figure 1, respectively.",  # 명시 참조 ("Figure 1")
    "As depicted in Fig. 1, the results improve.",      # 명시 참조 ("Fig. 1" 표기)
    "This paragraph is about something unrelated.",     # 무관 문단
    "See Figure 10 for the appendix chart.",            # Figure 10 ≠ Figure 1 (경계 검증)
]


def test_match_figure_golden_explicit():
    grounding_input = _make_input("Figure 1", GOLDEN_TEXTS)
    output = match_figure(grounding_input)

    assert output.figure_id == grounding_input.figure.id
    matched_para_ids = {m.paragraph_id for m in output.matches}
    expected_ids = {grounding_input.paragraphs[1].id, grounding_input.paragraphs[2].id}
    assert matched_para_ids == expected_ids, "명시 참조 2건만 매칭되어야 함 (캡션·무관·Figure 10 제외)"
    for m in output.matches:
        assert m.match_type == "explicit_reference"
        assert m.relevance_score == 1.0
        assert m.quote_span is not None


def test_quote_span_points_to_reference():
    refs = find_explicit_references("Figure 1", GOLDEN_TEXTS)
    for ref in refs:
        text = GOLDEN_TEXTS[ref.paragraph_index]
        quoted = text[ref.quote_span[0] : ref.quote_span[1]]
        assert quoted.lower().replace(".", "").startswith("fig")
        assert quoted.rstrip().endswith("1")


def test_caption_paragraph_never_matches():
    """캡션 자신은 어떤 표기('Figure 1:'/'Fig. 2.')든 매칭 후보에서 제외 (M3 Step 0 기록)."""
    texts = ["Figure 2. A building block.", "Fig. 2: another caption style."]
    assert find_explicit_references("Figure 2", texts) == []


def test_unpunctuated_caption_excluded_but_body_reference_kept():
    """무구두점 캡션(2026-07-14 지원)도 매칭에서 제외하되, 같은 접두의 '긴 본문 참조
    문장'(가짜 캡션, 150자 초과)은 계속 매칭 대상이어야 한다 — paper2 골든의 explicit
    힌트('Fig. 6 (middle) shows...')가 이 케이스다."""
    short_caption = "Fig. 2 waveform of a spoken digit belonging to the class (seven)"
    long_body_ref = (
        "Fig. 2 (middle) shows the behaviors of the networks. Also similar to the other "
        "cases, our models manage to overcome the optimization difficulty and demonstrate "
        "accuracy gains when the depth increases beyond one hundred layers."
    )
    refs = find_explicit_references("Figure 2", [short_caption, long_body_ref])
    assert [r.paragraph_index for r in refs] == [1], "짧은 캡션 제외, 긴 본문 참조는 유지"


def test_unparseable_figure_number_returns_empty():
    """'Figure ?N' 임시 번호(docs/data-model.md)는 명시 매칭 불가 — 빈 결과."""
    assert find_explicit_references("Figure ?3", GOLDEN_TEXTS) == []


def test_prompt_is_loadable_and_contains_contract():
    """prompt.md 분리(개발 원칙 6) + 필수 요소(출력 형식, 근거 없으면 no) 확인."""
    prompt = load_prompt()
    assert "is_relevant" in prompt
    assert "no로 답한다" in prompt


# --- 2단계 (의미 매칭) 기계 검증 — 가짜 임베더 + canned LLM (네트워크/비용 0) ---


class _FakeEmbedder:
    """텍스트별로 지정한 벡터를 돌려주는 가짜 임베더. 유사도를 정확히 통제한다."""

    name = "fake"
    dimension = 2

    def __init__(self, vectors: dict[str, list[float]], default=(0.0, 1.0)):
        self._vectors = vectors
        self._default = list(default)

    def embed(self, texts):
        return [self._vectors.get(t, self._default) for t in texts]


def test_semantic_candidates_threshold_and_exclusions():
    from app.agents.grounding_agent.node import find_semantic_candidates

    caption = "CAPTION"
    texts = [
        "A" * 100,   # 유사도 1.0 — 후보
        "B" * 100,   # 유사도 0.66 — 후보 (컷 0.65 바로 위)
        "C" * 100,   # 유사도 0.60 — 컷 미달
        "D" * 100,   # 유사도 1.0이지만 명시 매칭 완료 → 제외
        "short",     # 80자 미만 → 제외
        "Figure 9: caption paragraph. " + "x" * 80,  # 캡션 → 제외
    ]
    import math
    def vec(angle): return [math.cos(angle), math.sin(angle)]
    fake = _FakeEmbedder({
        caption: vec(0),
        texts[0]: vec(0),
        texts[1]: vec(math.acos(0.66)),
        texts[2]: vec(math.acos(0.60)),
        texts[3]: vec(0),
        texts[4]: vec(0),
        texts[5]: vec(0),
    })
    candidates = find_semantic_candidates(caption, texts, exclude_indices={3}, embedder=fake)
    indices = [i for i, _ in candidates]
    assert 0 in indices and 1 in indices, "컷(0.65) 이상 후보 포함"
    assert 2 not in indices, "컷 미달 제외"
    assert 3 not in indices, "명시 매칭 문단 제외"
    assert 4 not in indices and 5 not in indices, "짧은 문단·캡션 제외"


def test_match_figure_combines_stages_with_canned_llm():
    from app.core.llm.mock_provider import MockLLMProvider

    # 인용 게이트(B)를 통과하려면 reason이 문단 원문 12자+를 인용해야 하므로
    # 후보 문단을 실제 문장으로 둔다.
    para_yes = "The encoder maps an input sequence of symbol representations to a sequence of continuous representations."
    para_no = "This section discusses unrelated training hyperparameters and optimizer schedules in considerable detail."
    texts = [
        "The result is shown in Figure 1 clearly.",  # 명시 참조
        para_yes,                                     # 의미 후보 → LLM yes + 유효 인용
        para_no,                                      # 의미 후보 → LLM no
    ]
    grounding_input = _make_input("Figure 1", texts)
    caption = grounding_input.figure.caption
    fake = _FakeEmbedder({
        caption: [1.0, 0.0],
        para_yes: [1.0, 0.0],       # 유사도 1.0
        para_no: [0.94, 0.342],     # 유사도 ~0.94
    }, default=(0.0, 1.0))          # 명시 문단은 직교(후보 아님)
    llm = MockLLMProvider(canned_responses=[
        '{"is_relevant": true, "reason": "문단이 \\"maps an input sequence of symbol representations\\" 라고 설명한다"}',
        '{"is_relevant": false, "reason": "관련 없음"}',
    ])
    output = match_figure(grounding_input, llm=llm, embedder=fake)

    by_type = {}
    for m in output.matches:
        by_type.setdefault(m.match_type, []).append(m)
    assert len(by_type["explicit_reference"]) == 1
    assert len(by_type["semantic_similarity"]) == 1, "LLM yes인 후보만 매칭"
    semantic = by_type["semantic_similarity"][0]
    assert semantic.paragraph_id == grounding_input.paragraphs[1].id
    assert 0.99 <= semantic.relevance_score <= 1.0  # 코사인 유사도가 점수
    assert semantic.quote_span is None


def test_low_extraction_confidence_caps_semantic_score():
    from app.core.llm.mock_provider import MockLLMProvider

    para = "The decoder attends over all positions in the previous decoder layer through masked self-attention mechanisms."
    grounding_input = _make_input("Figure 1", [para])
    grounding_input.figure.extraction_confidence = 0.3  # 폴백 크롭 수준
    fake = _FakeEmbedder({grounding_input.figure.caption: [1.0, 0.0], para: [1.0, 0.0]})
    llm = MockLLMProvider(
        canned_responses=['{"is_relevant": true, "reason": "\\"attends over all positions\\" 라고 함"}']
    )
    output = match_figure(grounding_input, llm=llm, embedder=fake)
    assert output.matches[0].relevance_score == 0.3, "conf<0.5이면 점수가 conf로 상한"


def test_malformed_llm_response_treated_as_no():
    from app.agents.grounding_agent.node import _parse_verdict

    assert _parse_verdict('{"is_relevant": true, "reason": "x"}') == (True, "x")
    assert _parse_verdict("The answer is yes!")[0] is False, "JSON 아님 → 확신 없음 = no"
    assert _parse_verdict('prefix {"is_relevant": false} suffix')[0] is False
    assert _parse_verdict("{broken json")[0] is False


def test_quote_gate_rejects_only_fabrication():
    """B(완화, D3): 허위 인용만 거부. 인용 없음/패러프레이즈는 통과."""
    from app.agents.grounding_agent.node import _reason_not_fabricated

    para = "The encoder maps an input sequence to continuous representations."
    # 유효 인용 → 통과
    assert _reason_not_fabricated('문단이 "maps an input sequence" 라고 설명한다', para) is True
    # 인용 없는 패러프레이즈 → 통과 (완화의 핵심 — 정답을 버리지 않음)
    assert _reason_not_fabricated("문단이 인코더의 입력 처리 방식을 서술한다", para) is True
    # 허위 인용 (원문에 없는 문구) → 거부
    assert _reason_not_fabricated('"a completely fabricated quote here"', para) is False
    # 너무 짧은 인용은 fabrication 신호로 보지 않음 → 통과 (우연 일치 위험)
    assert _reason_not_fabricated('"the"', para) is True


def test_candidate_filter_excludes_bibliography_and_table_captions():
    """A: 서지 항목·Table 캡션은 후보에서 제외 (실측 오탐 원천)."""
    from app.agents.grounding_agent.node import find_semantic_candidates

    caption = "CAPTION"
    texts = [
        "[27] Ankur Parikh, Oscar Tackstrom. A decomposable attention model for inference.",  # 서지
        "Table 6. Classification error on the CIFAR-10 test set with data augmentation applied.",  # Table 캡션
        "The residual mapping is easier to optimize than the original unreferenced mapping here.",  # 본문
    ]
    fake = _FakeEmbedder({t: [1.0, 0.0] for t in [caption] + texts})  # 전부 유사도 1.0
    indices = [i for i, _ in find_semantic_candidates(caption, texts, set(), fake)]
    assert indices == [2], "서지·Table 캡션 제외, 본문만 후보"

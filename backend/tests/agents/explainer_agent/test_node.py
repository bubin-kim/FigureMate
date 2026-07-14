"""explainer_agent 단위 테스트 (docs/adding-an-agent.md 절차 7).

canned Vision 응답으로 네트워크 없이 검증한다. 핵심은 grounding 강제:
근거 없는 Figure에 none_found가 실제로 나오는지, 지어낸 근거가 걸러지는지.
"""
import uuid

from app.agents.explainer_agent.node import explain_figure, load_prompt
from app.agents.explainer_agent.schema import ExplainInput, MatchedParagraph
from app.core.llm.mock_provider import MockLLMProvider

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"fake"


def _input(figure_type="architecture", matches=None):
    return ExplainInput(
        figure_id=uuid.uuid4(),
        figure_number="Figure 1",
        caption="Figure 1: The Transformer - model architecture.",
        figure_type=figure_type,
        image_bytes=FAKE_PNG,
        matches=matches or [],
    )


def test_prompt_contains_required_rules():
    """prompt.md 필수 요소: Nx 반례, none_found 강제, observation vs citation, 한국어 출력."""
    prompt = load_prompt()
    assert "Nx" in prompt and "임의의 숫자" in prompt, "Nx→숫자 지어내기 반례 규칙"
    assert "none_found" in prompt
    assert "본문에서 설명하듯이" in prompt, "본문 인용 형식 금지(observation vs citation)"
    assert "한국어로 쓴다" in prompt, "설명 한국어 출력 규칙 (2026-07-14 사용자 요청)"


def test_none_found_enforced_when_no_matches():
    """근거 문단이 없으면 grounding.source='none_found'가 강제된다 (M4 핵심 DoD)."""
    canned = '{"summary": "s", "detailed_explanation": "d", "components": [], "grounding": []}'
    out = explain_figure(_input(matches=[]), llm=MockLLMProvider(canned_responses=[canned]))
    assert len(out.grounding) >= 1
    assert all(g.source == "none_found" for g in out.grounding)
    assert out.grounding[0].note  # 사용자에게 보일 문구


def test_fabricated_grounding_is_rejected():
    """모델이 매칭에 없는 paragraph_id를 근거로 대면 버려지고 none_found로 대체된다."""
    fake_pid = str(uuid.uuid4())
    canned = (
        '{"summary": "s", "detailed_explanation": "d", "components": [],'
        f' "grounding": [{{"source": "paragraph", "paragraph_id": "{fake_pid}", "note": null}}]}}'
    )
    out = explain_figure(_input(matches=[]), llm=MockLLMProvider(canned_responses=[canned]))
    assert all(g.source == "none_found" for g in out.grounding), "지어낸 근거는 버려야 함"


def test_valid_grounding_is_kept():
    """실제 매칭된 paragraph_id를 근거로 대면 그대로 유지된다."""
    m = MatchedParagraph(
        paragraph_id=uuid.uuid4(), text="The encoder and decoder...",
        match_type="explicit_reference", relevance_score=1.0,
    )
    canned = (
        '{"summary": "s", "detailed_explanation": "d", "components": [],'
        f' "grounding": [{{"source": "paragraph", "paragraph_id": "{m.paragraph_id}", "note": null}}]}}'
    )
    out = explain_figure(_input(matches=[m]), llm=MockLLMProvider(canned_responses=[canned]))
    para_refs = [g for g in out.grounding if g.source == "paragraph"]
    assert len(para_refs) == 1
    assert para_refs[0].paragraph_id == m.paragraph_id


def test_architecture_components_parsed():
    canned = (
        '{"summary": "s", "detailed_explanation": "d",'
        ' "components": [{"label": "Multi-Head Attention", "role": "r",'
        ' "plain_explanation": "p", "grounding": []}], "grounding": []}'
    )
    out = explain_figure(_input(figure_type="architecture", matches=[]),
                         llm=MockLLMProvider(canned_responses=[canned]))
    assert len(out.components) == 1
    assert out.components[0].label == "Multi-Head Attention"
    # 컴포넌트 grounding도 근거 없으면 none_found
    assert out.components[0].grounding[0].source == "none_found"


def test_plot_type_has_no_components():
    canned = ('{"summary": "s", "detailed_explanation": "d",'
              ' "components": [{"label": "x", "role": "r", "plain_explanation": "p"}], "grounding": []}')
    out = explain_figure(_input(figure_type="plot", matches=[]),
                         llm=MockLLMProvider(canned_responses=[canned]))
    assert out.components == [], "plot 타입은 components를 비운다"


def test_malformed_json_still_produces_honest_output():
    """JSON이 깨져도 죽지 않고, none_found + 원문 일부로 정직한 산출물을 낸다.
    parse_ok=False로 표시되어 호출부(pipeline)가 재시도할 수 있다."""
    out = explain_figure(_input(matches=[]),
                         llm=MockLLMProvider(canned_responses=["설명이 그냥 평문으로 왔다"]))
    assert out.detailed_explanation
    assert all(g.source == "none_found" for g in out.grounding)
    assert out.parse_ok is False, "파싱 실패가 플래그로 노출되어야 함"


def test_parse_ok_true_on_valid_json():
    out = explain_figure(_input(matches=[]),
                         llm=MockLLMProvider(canned_responses=['{"summary":"s","detailed_explanation":"d"}']))
    assert out.parse_ok is True


def test_model_used_recorded():
    out = explain_figure(_input(matches=[]),
                         llm=MockLLMProvider(canned_responses=['{"summary":"s","detailed_explanation":"d"}']))
    assert out.model_used == "mock:mock"

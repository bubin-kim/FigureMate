"""explainer_agent — Figure 설명 생성 Agent (M4).

단일 책임: Figure 하나를 이미지 + 근거 문단에 기반해 설명한다.

구성 (grounding_agent와 동일한 패턴):
- Vision LLM(Provider Layer 경유)에 이미지 + 캡션 + 매칭 근거 문단을 넣어 구조화 설명 생성.
- 근거가 없으면(matches 비어 있음) source="none_found"를 강제한다 — 지어내지 않는다.
- 순수 함수 유지 (DB/스토리지 무접촉). Provider 주입 가능(테스트: canned Vision 응답).
- LangGraph 미조립 상태에서 pipeline이 직접 호출하며, M4 Step 6에서 그래프 노드로 감싼다.

grounding 강제 로직 (M3의 "확신 없으면 no"와 같은 계열의 안전장치):
- 모델이 뭐라고 답하든, matches가 비어 있으면 최종 grounding에 none_found가 반드시 들어간다.
- 모델이 grounding을 비워서 주거나 JSON이 깨져도, 코드가 안전한 기본값(none_found)으로 보정한다.
  근거 없는 설명이 "근거 있는 것처럼" 저장되는 일을 코드 레벨에서 막는다.
"""
from __future__ import annotations

import base64
import json as _json
from functools import lru_cache
from pathlib import Path

from app.agents.explainer_agent.schema import ExplainInput, ExplainOutput
from app.core.llm import (
    CompletionRequest,
    ImagePart,
    LLMProvider,
    Message,
    TextPart,
    get_llm_provider,
)
from app.schemas.explanation import ExplanationComponent, GroundingRef

_NONE_FOUND_NOTE = (
    "본문에서 이 Figure를 직접 설명하는 부분을 찾지 못했습니다. "
    "아래 설명은 캡션과 그림 관찰에 근거합니다."
)


@lru_cache
def load_prompt() -> str:
    """prompt.md의 시스템 프롬프트 (개발 원칙 6: 프롬프트는 코드와 분리)."""
    return (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def _build_user_message(explain_input: ExplainInput) -> Message:
    lines = [
        f"[Figure 번호] {explain_input.figure_number}",
        f"[타입] {explain_input.figure_type}",
        f"[캡션] {explain_input.caption}",
    ]
    if explain_input.matches:
        lines.append("\n[매칭된 본문 근거 문단]")
        for m in explain_input.matches:
            lines.append(f"- (paragraph_id={m.paragraph_id}, {m.match_type}) {m.text}")
    else:
        lines.append("\n[매칭된 본문 근거 문단] 없음 — none_found로 처리할 것")
    # 마지막 지시가 소형 모델에서 가장 잘 지켜진다 — 한국어·문체·JSON 규칙을 끝에 한 번 더.
    # 문체는 합쇼체(존댓말) 표준 (2026-07-14 실측: 7b가 특정 Figure에서 '-다'체 지시를
    # 3회 재시도 모두 무시할 만큼 합쇼체 성향이 강함 — 모델 성향에 맞춰 표준을 정했다)
    lines.append(
        "\n[지시] 설명(summary, detailed_explanation, role, plain_explanation)은 반드시 한국어로 작성한다."
        ' 모든 문장은 "~합니다/~입니다"(존댓말)로 끝낸다 ("~한다/~이다"체 금지).'
        " 중국어 한자·키릴 문자를 쓰지 않는다. 유효한 JSON만 출력한다."
    )
    parts = [
        TextPart(text="\n".join(lines)),
        ImagePart(data=explain_input.image_bytes, media_type=explain_input.image_media_type),
    ]
    return Message(role="user", parts=parts)


def _parse_response(text: str) -> dict:
    """모델 응답에서 JSON 객체를 파싱한다. 실패 시 빈 dict (호출부가 안전 보정)."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        parsed = _json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def _coerce_grounding(raw: object, valid_ids: set[str], has_matches: bool) -> list[GroundingRef]:
    """모델이 준 grounding을 안전하게 GroundingRef 리스트로 만든다.

    - paragraph_id가 실제 매칭된 문단 id가 아니면(지어낸 근거) 버린다.
    - 유효한 paragraph 근거가 하나도 없으면 none_found 항목 1개를 넣는다.
      (근거 없는 설명이 근거 있는 것처럼 저장되는 것을 코드가 막는다.)
    """
    refs: list[GroundingRef] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            source = item.get("source")
            pid = item.get("paragraph_id")
            if source == "paragraph" and pid and str(pid) in valid_ids:
                refs.append(GroundingRef(paragraph_id=pid, source="paragraph", note=item.get("note")))
            elif source == "caption":
                refs.append(GroundingRef(paragraph_id=None, source="caption", note=item.get("note")))
    if not any(r.source == "paragraph" for r in refs) and not has_matches:
        # 근거 문단이 애초에 없었던 케이스 → none_found 강제
        return [GroundingRef(paragraph_id=None, source="none_found", note=_NONE_FOUND_NOTE)]
    if not refs:
        # 매칭은 있었는데 모델이 근거를 안 준 경우도 none_found로 정직하게 표시
        return [GroundingRef(paragraph_id=None, source="none_found", note=_NONE_FOUND_NOTE)]
    return refs


def _coerce_components(raw: object, valid_ids: set[str], has_matches: bool) -> list[ExplanationComponent]:
    components: list[ExplanationComponent] = []
    if not isinstance(raw, list):
        return components
    for item in raw:
        if not isinstance(item, dict) or not item.get("label"):
            continue
        components.append(
            ExplanationComponent(
                label=str(item.get("label", "")),
                role=str(item.get("role", "")),
                plain_explanation=str(item.get("plain_explanation", "")),
                grounding=_coerce_grounding(item.get("grounding"), valid_ids, has_matches),
            )
        )
    return components


def explain_figure(
    explain_input: ExplainInput,
    llm: LLMProvider | None = None,
    temperature: float = 0.0,
) -> ExplainOutput:
    """Figure 이미지와 매칭 근거로 근거 있는 설명을 생성한다.

    matches가 비어 있으면 근거 없음을 명시하는 설명을 만든다 — 근거를 조작하지 않는다.
    Provider는 주입 가능(테스트: canned Vision 응답). 기본은 환경변수 설정을 따른다.
    """
    # vision=True: explainer는 이미지 입력이 필수라 Vision 모델을 쓴다 (ollama는 OLLAMA_VISION_MODEL).
    llm = llm or get_llm_provider(vision=True)
    request = CompletionRequest(
        system=load_prompt(),
        messages=[_build_user_message(explain_input)],
        # 4096 (M4 Step 5 실측): qwen2.5vl:3b가 verbose해 아키텍처형(components 다수)에서
        # 1024·2048 모두 JSON을 중간에 잘라 파싱 실패시켰다. 프롬프트에도 간결성 지시를 둠.
        max_tokens=4096,
        # temperature는 호출부(재시도 루프)가 올릴 수 있다 — temp=0에서 특정 Figure가
        # 일관되게 깨진 JSON을 내는 불량 모드에 갇히는 실측 사례 대응 (2026-07-14).
        temperature=temperature,
    )
    response = llm.complete(request)
    data = _parse_response(response.text)

    valid_ids = {str(m.paragraph_id) for m in explain_input.matches}
    has_matches = bool(explain_input.matches)
    summary = str(data.get("summary") or "").strip()
    detailed = str(data.get("detailed_explanation") or "").strip()
    if not summary and not detailed:
        # 파싱 완전 실패 시에도 최소한의 정직한 산출물 (원문 앞부분 + none_found)
        detailed = response.text.strip()[:2000]

    components = (
        _coerce_components(data.get("components"), valid_ids, has_matches)
        if explain_input.figure_type == "architecture"
        else []
    )
    grounding = _coerce_grounding(data.get("grounding"), valid_ids, has_matches)

    return ExplainOutput(
        figure_id=explain_input.figure_id,
        figure_type=explain_input.figure_type,
        summary=summary or detailed[:200],
        detailed_explanation=detailed or summary,
        components=components,
        grounding=grounding,
        model_used=f"{response.provider}:{response.model}",
        parse_ok=bool(data),  # 빈 dict = 파싱 실패 (호출부가 재시도 판단)
    )

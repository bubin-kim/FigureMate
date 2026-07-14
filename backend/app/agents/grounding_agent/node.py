"""grounding_agent — Figure ↔ 본문 매칭 Agent (M3).

단일 책임: "이 Figure를 설명/참조하는 본문 문단"을 찾는다.

구성 (docs/milestones/M3.md):
- 1단계 (이 파일의 find_explicit_references): 명시적 참조 탐지 — **LLM 없는 결정론적
  정규식 로직** (개발 원칙 5: 의미 판단이 아니므로 LLM에 맡기지 않는다).
- 2단계 (Step 4에서 추가): 임베딩 유사도 후보 + LLM 검증 — Provider Layer 경유.
- LangGraph 조립은 M4로 미뤄짐 (M3.md 착수 전 결정 #3) — 이 모듈의 함수들은
  그래프 없이 API 라우트에서 직접 호출 가능한 순수 함수로 유지한다.

캡션 자신 제외 (M3 Step 0 실측 기록): M1 파서가 부록을 References 섹션으로 흡수하므로
Figure 3~5의 캡션 텍스트("Figure N: ...")가 일반 문단으로 DB에 존재한다. 캡션은 그 Figure의
"참조"가 아니라 Figure 자신이므로 매칭 후보에서 제외한다 — 판별 규칙은 figure_extractor의
캡션 판별과 동일 ("Figure N" + 구두점 ':' 또는 '.').
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import json as _json
import math

from app.agents.grounding_agent.schema import (
    GroundingInput,
    GroundingOutput,
    MatchResult,
)
from app.core.llm import (
    CompletionRequest,
    EmbeddingProvider,
    LLMProvider,
    Message,
    get_embedding_provider,
    get_llm_provider,
)

# figure_extractor._CAPTION_RE와 동일한 규칙 (캡션 = "Figure N" + 구두점).
_CAPTION_RE = re.compile(r"^(Figure|Fig\.)\s+(\d+)\s*[.:]", re.IGNORECASE)
# 무구두점 캡션 스타일("Fig. 5 A window...", 2026-07-14 지원)도 매칭 후보에서 제외한다.
# 레이아웃 정보가 없는 이 계층에서는 길이 컷(A)만 적용 — 실측상 진짜 무구두점 캡션은
# 31~109자, 가짜 캡션 본문("Fig. 6 (middle) shows...")은 216자+라 150자 컷으로 구분된다.
# (가짜 캡션 문단은 제외되지 않아야 함 — paper2 골든의 explicit 매칭 대상이다.)
_CAPTION_LOOSE_RE = re.compile(r"^(Figure|Fig\.)\s+(\d+)\s+\S", re.IGNORECASE)
_LOOSE_CAPTION_MAX_CHARS = 150


def _is_caption_paragraph(text: str) -> bool:
    if _CAPTION_RE.match(text):
        return True
    return bool(_CAPTION_LOOSE_RE.match(text)) and len(text) <= _LOOSE_CAPTION_MAX_CHARS

# Figure.figure_number 필드 파싱 ("Figure 3" → 3). "Figure ?N" 임시 번호는 매칭 불가.
_FIGURE_NUMBER_RE = re.compile(r"^Figure\s+(\d+)$")


@dataclass
class ExplicitReference:
    """한 문단 안에서 발견된 명시적 Figure 참조.

    paragraph_index: 호출자가 넘긴 문단 리스트의 인덱스 (DB 무관 — 순수 함수 유지).
    quote_span: 문단 텍스트 내 참조 위치 (시작, 끝) — FigureTextMatch.quote_span에 기록.
    """

    paragraph_index: int
    quote_span: tuple[int, int]


def find_explicit_references(
    figure_number: str, paragraph_texts: Sequence[str]
) -> list[ExplicitReference]:
    """본문 문단들에서 해당 Figure의 명시적 참조("Figure N", "Fig. N")를 찾는다.

    - 캡션 문단(_CAPTION_RE 매치)은 어떤 Figure의 것이든 후보에서 제외한다.
    - 한 문단에 같은 Figure 참조가 여러 번 나와도 매칭은 1건 (첫 번째 위치를 quote_span으로).
    - "Figure 1"이 "Figure 10~19"에 오매칭되지 않도록 숫자 뒤 경계를 요구한다.
    - 복수형("Figures 3 and 4")은 탐지하지 않는다 — Step 0 골든도 같은 기준으로 작성됨.
      실논문에서 사례가 확인되면 골든과 함께 확장한다.
    """
    number_match = _FIGURE_NUMBER_RE.match(figure_number)
    if not number_match:
        return []  # "Figure ?N" 등 번호 파싱 실패 → 명시 매칭 불가 (의미 매칭만 가능)
    n = number_match.group(1)
    reference_pattern = re.compile(rf"\b(?:Figure|Fig\.)\s*{n}(?!\d)", re.IGNORECASE)

    references: list[ExplicitReference] = []
    for index, text in enumerate(paragraph_texts):
        if _is_caption_paragraph(text):
            continue  # 캡션 자신 (부록 캡션이 References 문단으로 존재·무구두점 스타일 포함)
        found = reference_pattern.search(text)
        if found:
            references.append(
                ExplicitReference(
                    paragraph_index=index, quote_span=(found.start(), found.end())
                )
            )
    return references


@lru_cache
def load_prompt() -> str:
    """prompt.md의 시스템 프롬프트 (개발 원칙 6: 프롬프트는 코드와 분리).
    2단계 LLM 검증(Step 4)에서 사용한다."""
    return (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


# --- 2단계(의미 매칭) 파라미터 — 실측 근거 (M3 Step 4, 2026-07-13, 사용자 승인) ---
# 두 논문 250개 문단 분포 측정: 정답(명시 매칭 35건) 유사도 min 0.532~max 0.845,
# 배경 중앙 0.576/0.627, p90 0.693/0.723.
# top-k: 초기 15에서 20으로 상향(C, 2026-07-13). 실제 캡션 텍스트로는 Fig3 힌트가 15위 컷
# (0.704) 바로 아래(0.696)로 밀려 탈락했음 — 20으로 넓혀 재포함하되, 오탐은 아래 A/B로 막는다.
_TOP_K = 20
_MIN_SIMILARITY = 0.65
# 80자 미만 제외: 표 조각 필터 (실측: paper2 문단 62%가 표 조각으로 걸러짐 — M1 한계 #1 완화)
_MIN_PARAGRAPH_CHARS = 80
# extraction_confidence 전파 (M3 조건 #3): 캡션-이미지 짝이 불확실한 Figure(conf<0.5)는
# 의미 매칭 점수가 그 conf를 넘지 못한다 (불확실성이 하류로 전파되어야 함).
_CONFIDENCE_CAP_BELOW = 0.5

# A(2026-07-13): 후보 단계에서 결정론적으로 걸러내는 비(非)본문 패턴.
# 실측에서 서지 항목("[27] Ankur Parikh, ...")과 Table 캡션("Table 6. ...")이 LLM 검증을
# 다수 통과하는 오탐 원천이었다 — 애초에 후보에서 배제한다.
_BIBLIOGRAPHY_RE = re.compile(r"^\[\d+\]\s")           # "[27] Author, Title..."
_TABLE_CAPTION_RE = re.compile(r"^Table\s+\d+\s*[.:]", re.IGNORECASE)  # "Table 6. ..."

# B(2026-07-13, D3로 완화): 인용 게이트. 초기엔 "인용이 원문에 존재해야만 통과"로 강했으나,
# 약한 모델이 패러프레이즈하면 정답까지 버려 재현율이 붕괴했다(Fig5 1위 정답 거부). 완화 후
# 기준은 **허위 인용만 차단**: reason이 따옴표로 문구를 인용했는데 그게 원문에 없으면(fabrication)
# 거부, 인용이 없으면 판정을 신뢰한다. 인용은 언어에 무관한 fabrication 신호로만 쓴다
# (reason이 한국어여도 인용 문구는 영어 원문에서 복사되므로).
_QUOTE_RE = re.compile(r'["“”](.+?)["“”]')
_MIN_QUOTE_CHARS = 12


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _is_non_body(text: str) -> bool:
    """본문이 아닌 문단(서지 항목·Table 캡션·Figure 캡션)인가 — 의미 매칭 후보에서 제외."""
    return bool(
        _is_caption_paragraph(text)
        or _BIBLIOGRAPHY_RE.match(text)
        or _TABLE_CAPTION_RE.match(text)
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def _reason_not_fabricated(reason: str, paragraph_text: str) -> bool:
    """B(완화): reason이 허위 인용을 하지 않았는가.

    - reason에 12자 이상 인용이 있으면, 그중 하나라도 원문에 실존해야 True.
      전부 원문에 없으면(=지어낸 인용) False로 거부.
    - 인용이 아예 없으면 True (판정을 신뢰 — 패러프레이즈 정답을 버리지 않기 위함).
    """
    quotes = [_normalize(q) for q in _QUOTE_RE.findall(reason)]
    meaningful = [q for q in quotes if len(q) >= _MIN_QUOTE_CHARS]
    if not meaningful:
        return True
    body = _normalize(paragraph_text)
    return any(q in body for q in meaningful)


def _parse_verdict(response_text: str) -> tuple[bool, str]:
    """LLM 검증 응답에서 (is_relevant, reason)를 파싱한다. 파싱 실패는 '확신 없음 = no'로
    처리한다 (prompt.md의 원칙과 동일 — 근거가 확인되지 않으면 매칭하지 않는다)."""
    start, end = response_text.find("{"), response_text.rfind("}")
    if start == -1 or end <= start:
        return False, ""
    try:
        data = _json.loads(response_text[start : end + 1])
        return bool(data.get("is_relevant", False)), str(data.get("reason", ""))
    except (ValueError, AttributeError):
        return False, ""


def find_semantic_candidates(
    caption: str,
    paragraph_texts: Sequence[str],
    exclude_indices: set[int],
    embedder: EmbeddingProvider,
) -> list[tuple[int, float]]:
    """캡션과 의미가 유사한 문단 후보를 (문단 인덱스, 유사도)로 반환한다.

    - 캡션·서지 항목·Table 캡션(A) / 80자 미만(표 조각) / 명시 매칭된 문단은 제외.
    - top-20 AND 유사도 ≥0.65 (위 파라미터 주석의 실측 근거).
    """
    eligible = [
        (i, t)
        for i, t in enumerate(paragraph_texts)
        if i not in exclude_indices
        and len(t) >= _MIN_PARAGRAPH_CHARS
        and not _is_non_body(t)
    ]
    if not eligible:
        return []
    caption_vec = embedder.embed([caption])[0]
    paragraph_vecs = embedder.embed([t for _, t in eligible])
    scored = sorted(
        ((_cosine(caption_vec, v), i) for v, (i, _) in zip(paragraph_vecs, eligible)),
        reverse=True,
    )
    return [(i, score) for score, i in scored[:_TOP_K] if score >= _MIN_SIMILARITY]


def verify_candidate(caption: str, paragraph_text: str, llm: LLMProvider) -> bool:
    """LLM 검증(prompt.md 계약) + 인용 게이트(B): is_relevant가 true여도 reason이 인용한
    문구가 문단 원문에 실존해야 매칭을 인정한다."""
    request = CompletionRequest(
        system=load_prompt(),
        messages=[Message.user_text(f"[Figure 캡션]\n{caption}\n\n[문단]\n{paragraph_text}")],
        max_tokens=200,
        temperature=0.0,
    )
    is_relevant, reason = _parse_verdict(llm.complete(request).text)
    return is_relevant and _reason_not_fabricated(reason, paragraph_text)


def match_figure(
    grounding_input: GroundingInput,
    llm: LLMProvider | None = None,
    embedder: EmbeddingProvider | None = None,
) -> GroundingOutput:
    """Agent 진입 함수 — Figure 하나에 대한 매칭을 수행한다.

    1단계: 명시적 참조 (결정론, score=1.0) → 2단계: 의미 매칭 (임베딩 top-15·≥0.65
    후보 → LLM 검증 통과 시 score=코사인 유사도).

    Provider는 주입 가능(테스트: 가짜 임베더 + canned LLM)하며, 기본은 환경변수 설정을
    따른다 (mock 기본 — mock 임베딩은 의미 유사도가 없어 2단계가 사실상 no-op이 되는
    것이 정상이고, 실품질은 EMBEDDING_PROVIDER=ollama에서 발휘된다).

    LangGraph 미조립 상태(M3.md 결정 #3)에서 API 라우트가 직접 호출하는 시그니처이며,
    M4에서 그래프 노드로 감쌀 때는 PipelineState에서 GroundingInput을 꾸리는 어댑터만
    씌우면 된다 (순수 함수 — DB/스토리지 무접촉).
    """
    figure = grounding_input.figure
    texts = [p.text for p in grounding_input.paragraphs]

    explicit_refs = find_explicit_references(figure.figure_number, texts)
    matches = [
        MatchResult(
            figure_id=figure.id,
            paragraph_id=grounding_input.paragraphs[ref.paragraph_index].id,
            match_type="explicit_reference",
            relevance_score=1.0,  # 정규식 확신 (docs/data-model.md: explicit은 신뢰도 최상)
            quote_span=ref.quote_span,
        )
        for ref in explicit_refs
    ]

    embedder = embedder or get_embedding_provider()
    llm = llm or get_llm_provider()
    explicit_indices = {ref.paragraph_index for ref in explicit_refs}
    for index, similarity in find_semantic_candidates(
        figure.caption, texts, explicit_indices, embedder
    ):
        if verify_candidate(figure.caption, texts[index], llm):
            score = similarity
            if figure.extraction_confidence < _CONFIDENCE_CAP_BELOW:
                score = min(score, figure.extraction_confidence)
            matches.append(
                MatchResult(
                    figure_id=figure.id,
                    paragraph_id=grounding_input.paragraphs[index].id,
                    match_type="semantic_similarity",
                    relevance_score=round(score, 4),
                    quote_span=None,
                )
            )
    return GroundingOutput(figure_id=figure.id, matches=matches)

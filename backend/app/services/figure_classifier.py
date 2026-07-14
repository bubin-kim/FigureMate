"""Figure 타입 판별 (M4 Step 3).

Figure를 architecture | plot | qualitative | other로 분류한다. **Vision 호출을 추가하지
않는다** (M4.md 방침: Figure당 Vision 호출을 늘리지 않는다) — 캡션 키워드 휴리스틱만 쓰는
결정론적 서비스다 (개발 원칙 5: 결정론적 판단은 LLM에 맡기지 않는다).

분류 우선순위 (plot → qualitative → architecture → other):
- plot: 학습/오차 곡선, 표준편차 등 "수치 경향"을 그린 그래프. 가장 명확한 키워드라 먼저 본다.
- qualitative: "example of ...", attention head 시각화 등 정성적 예시.
- architecture: 구조도/다이어그램/메커니즘 도해. MVP 우선 지원 타입(data-model.md)이라
  구조·메커니즘 단어가 있으면 여기로.
- other: 위 어디에도 안 걸리는 경우.

애매한 경우(other로 떨어지는 경우)는 M4.md 방침대로 별도 Vision 호출을 만들지 않고,
explainer_agent 프롬프트가 타입도 함께 판단하도록 넘긴다(Step 4에서 override 가능).

이미지 종횡비도 신호 후보로 검토했으나(M4.md "이미지의 종횡비 등"), 두 샘플 논문의
아키텍처형이 세로형(Fig 1)·가로형(Fig 2)으로 섞여 있어 종횡비만으로는 분리되지 않았다 —
캡션 키워드만으로 12개 Figure가 전부 올바르게 분류되어 종횡비는 도입하지 않았다(향후 확장 여지).
"""
from __future__ import annotations

import re

from app.schemas.explanation import FigureType

# 각 타입의 키워드 (소문자 부분 문자열 매칭). 우선순위 순서대로 검사한다.
_PLOT_KEYWORDS = (
    "training", "error", "accuracy", "loss", "std", "standard deviation",
    "curve", " rate", "convergence", " vs ",
)
_QUALITATIVE_KEYWORDS = (
    "example of", "visualization", "visualisation", "qualitative", "sample",
    "attention head", "mechanism following", "involved in", "exhibit behaviour",
    "exhibit behavior",
)
_ARCHITECTURE_KEYWORDS = (
    "architecture", "building block", "block", "framework", "network", "module",
    "residual function", "residual learning", "diagram", "pipeline", "structure",
    "attention", "encoder", "decoder", "convolution", "model",
)


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def classify_figure(caption: str) -> FigureType:
    """캡션으로 Figure 타입을 판별한다 (Vision 호출 없음).

    caption은 "Figure N: ..." 형태의 전체 캡션. 번호/구두점 접두는 판별에 영향 없다.
    """
    text = re.sub(r"\s+", " ", caption).strip().lower()
    if _matches(text, _PLOT_KEYWORDS):
        return "plot"
    if _matches(text, _QUALITATIVE_KEYWORDS):
        return "qualitative"
    if _matches(text, _ARCHITECTURE_KEYWORDS):
        return "architecture"
    return "other"

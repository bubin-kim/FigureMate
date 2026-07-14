"""LangGraph 파이프라인 상태 (M4 Step 6). docs/architecture.md 4절 참고.

PipelineState가 단일 진실 원천이다 — 파이프라인 각 단계가 공유하는 상태를 여기서 정의한다.
새 필드는 이 파일에만 추가한다.

설계 노트: 각 stage는 결과를 DB에 저장하므로(pipeline.py), 상태에는 큰 산출물을 싣지 않고
식별자와 흐름 제어 정보만 담는다. DB 세션은 상태가 아니라 config["configurable"]["db"]로
노드에 전달한다(직렬화 대상이 아님).
"""
from __future__ import annotations

from typing import TypedDict


class PipelineState(TypedDict):
    paper_id: str
    figure_ids: list[str]   # (예약) explain을 fan-out으로 확장할 때 대상 목록
    failed: bool            # 앞 단계 실패 시 True → 이후 단계 건너뜀

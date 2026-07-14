"""LangGraph 파이프라인 조립 (M4 Step 6).

services/pipeline.py의 stage 함수들을 노드로 감싼다 (로직 재작성 아님 — M4.md 방침).
parse → extract → match → explain → finalize의 선형 그래프이며, parse/extract 실패 시
조건부 엣지로 END로 빠진다 (architecture.md 4절: MVP 그래프는 조건부 분기 없이 선형에 가깝게
시작하고 필요해질 때 확장).

explain은 단일 노드로 Figure들을 순차 처리한다 (Send fan-out 아님). 이유(M4.md 한계 #3,
Step 6 실측): sync fan-out은 단일 워커 스레드에서 순차 실행이라 병렬 이득이 없고, 여러
브랜치가 한 세션에서 commit을 재진입 호출해 IllegalStateChangeError를 유발했다. 로컬 단일
GPU ollama가 동시 호출에 marginal(0.71)하므로 순차가 병렬과 동등하다. Figure별 로직은
explain_stage_one으로 분리되어 있어, async + 서버측 동시성 Provider로 전환할 때 fan-out으로
확장할 여지는 열려 있다.

DB 세션은 config["configurable"]["db"]로 노드에 전달한다 (직렬화 대상 아님).
"""
from __future__ import annotations

import uuid

from langgraph.graph import END, START, StateGraph

from app.graph.state import PipelineState
from app.services import pipeline


def _db(config):
    return config["configurable"]["db"]


def parse_node(state: PipelineState, config) -> dict:
    ok = pipeline.parse_stage(uuid.UUID(state["paper_id"]), _db(config))
    return {"failed": not ok}


def extract_node(state: PipelineState, config) -> dict:
    ok = pipeline.extract_stage(uuid.UUID(state["paper_id"]), _db(config))
    return {"failed": not ok}


def match_node(state: PipelineState, config) -> dict:
    pipeline.match_stage(uuid.UUID(state["paper_id"]), _db(config))
    return {}


def explain_node(state: PipelineState, config) -> dict:
    pipeline.explain_stage(uuid.UUID(state["paper_id"]), _db(config))
    return {}


def finalize_node(state: PipelineState, config) -> dict:
    pipeline.finalize_stage(uuid.UUID(state["paper_id"]), _db(config))
    return {}


def _route_after_parse(state: PipelineState):
    return END if state["failed"] else "extract"


def _route_after_extract(state: PipelineState):
    return END if state["failed"] else "match"


def build_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("parse", parse_node)
    graph.add_node("extract", extract_node)
    graph.add_node("match", match_node)
    graph.add_node("explain", explain_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "parse")
    graph.add_conditional_edges("parse", _route_after_parse, ["extract", END])
    graph.add_conditional_edges("extract", _route_after_extract, ["match", END])
    graph.add_edge("match", "explain")
    graph.add_edge("explain", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


# 컴파일된 그래프는 상태가 없으므로 모듈 수준에서 한 번만 만든다.
_COMPILED = build_graph()


def run_pipeline(paper_id: uuid.UUID, db) -> None:
    """전체 파이프라인을 그래프로 실행한다 (pipeline.process_paper의 실제 구현)."""
    _COMPILED.invoke(
        {"paper_id": str(paper_id), "figure_ids": [], "failed": False},
        config={"configurable": {"db": db}},
    )

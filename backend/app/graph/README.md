# LangGraph 파이프라인 (M4에서 구현됨)

전체 처리 파이프라인을 LangGraph `StateGraph`로 조립한다.

- `state.py` — `PipelineState` (TypedDict). 단일 진실 원천. 상태에는 식별자·흐름 제어만 담고,
  각 단계 산출물은 DB에 저장한다. DB 세션은 `config["configurable"]["db"]`로 노드에 전달.
- `pipeline_graph.py` — 그래프 조립. `services/pipeline.py`의 stage 함수를 노드로 감싼다
  (로직 재작성 아님). 진입점은 `run_pipeline(paper_id, db)`이며 `pipeline.process_paper`가 호출.

구조 (선형 + 실패 조건부 엣지):

```
START → parse → (실패?END) → extract → (실패?END) → match → explain → finalize → END
```

- 앞 3단계(parse/extract/match, M1~M3)는 기존 로직을 노드로 감싸기만 함.
- explain(M4)은 단일 노드에서 Figure들을 순차 처리 (Send fan-out 아님 — 이유는
  `docs/milestones/M4.md` 알려진 한계 #3: sync fan-out 무이득 + 세션 재진입 문제).
- 부분 실패: 개별 Figure의 매칭/설명 실패는 그 Figure만 건너뜀 (stage 함수 내부 try/except).

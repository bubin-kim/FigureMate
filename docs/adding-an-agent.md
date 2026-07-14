# 새 Agent 추가하기

FigureMate의 Agent는 LangGraph 그래프의 노드입니다. 새 기능이 필요할 때 기존 Agent에 책임을
욱여넣지 말고, 이 절차를 따라 새 Agent를 추가하세요.

## 언제 새 Agent가 필요한가 / 언제 필요 없는가

**필요한 경우**: "의미를 판단"하거나 "추론"해야 하는 새로운 종류의 작업이 생겼을 때.
예: 발표 스크립트를 생성하는 기능 → `presentation_agent` 신설.

**필요 없는 경우**: 결정론적 로직(정렬, 필터링, 포맷 변환, 단순 DB 조회)이라면 `app/services/`에
일반 함수로 추가하세요. LLM이 필요 없는 일에 Agent를 만들지 않습니다.

**기존 Agent를 확장해도 되는 경우**: 새 책임이 기존 Agent의 책임과 완전히 같은 종류일 때만.
애매하면 분리하는 쪽을 기본값으로 합니다 — 나중에 합치는 것보다 나중에 나누는 게 더 어렵습니다.

## 절차

### 1. 폴더 생성 (기존 Agent 복제로 시작)

```bash
cp -r backend/app/agents/grounding_agent backend/app/agents/<new_agent_name>
```

폴더 구조:
```
backend/app/agents/<new_agent_name>/
├── node.py       # LangGraph 노드 함수
├── prompt.md      # 시스템 프롬프트 (LLM을 쓰는 경우)
└── schema.py      # 입출력 Pydantic 모델
```

### 2. `schema.py` 정의

이 Agent가 받는 입력과 반환하는 출력을 Pydantic 모델로 명확히 정의합니다.
`docs/data-model.md`에 이미 있는 모델을 재사용할 수 있으면 재사용하고, 새 모델이 필요하면
`docs/data-model.md`에도 추가합니다.

### 3. `prompt.md` 작성 (해당되는 경우)

시스템 프롬프트를 이 파일에 마크다운으로 작성합니다. 코드에 문자열로 박아넣지 않습니다.
프롬프트에는 반드시 다음을 포함합니다:
- 이 Agent의 단일 책임이 무엇인지
- 출력 형식 (JSON 스키마 등)
- grounding이 필요한 경우, "근거 없으면 지어내지 말 것" 명시

### 4. `node.py` 구현

```python
# 예시 형태
from app.graph.state import PipelineState
from .schema import NewAgentInput, NewAgentOutput

async def run(state: PipelineState) -> dict:
    input_data = NewAgentInput(...)  # state에서 필요한 부분 추출
    result = await call_claude(...)   # 또는 결정론적 로직
    output = NewAgentOutput.model_validate(result)
    return {"새로운_state_필드": output}
```

### 5. `state.py`에 필드 추가 (필요한 경우)

`backend/app/graph/state.py`의 `PipelineState`에 이 Agent의 출력을 담을 필드를 추가합니다.

### 6. `pipeline_graph.py`에 노드 등록

```python
from app.agents.<new_agent_name>.node import run as new_agent_run

graph.add_node("<new_agent_name>", new_agent_run)
graph.add_edge("<이전_노드>", "<new_agent_name>")
```

### 7. 테스트 작성

```
backend/tests/agents/<new_agent_name>/
├── test_node.py
└── fixtures/          # 골든 케이스 (입력 예시 + 기대 출력)
```

최소한 하나의 골든 케이스로 "정상 입력 → 기대하는 형태의 출력"을 검증합니다.

### 8. 문서 갱신

- `CLAUDE.md`의 "파이프라인 → Agent 매핑" 표에 한 줄 추가
- `docs/architecture.md`에 이 Agent가 파이프라인의 어느 단계인지 설명 추가

## 체크리스트

새 Agent PR을 올리기 전에 확인하세요:

- [ ] 이 Agent를 한 문장으로 설명할 때 "그리고"가 들어가지 않는가?
- [ ] `schema.py`에 입출력이 명확히 타입으로 정의되어 있는가?
- [ ] LLM을 쓰는 경우, 프롬프트가 `prompt.md`로 분리되어 있는가?
- [ ] 근거(grounding)가 필요한 출력이라면, 근거 없는 생성을 막는 장치가 있는가?
- [ ] 최소 1개의 골든 케이스 테스트가 있는가?
- [ ] `CLAUDE.md`와 `docs/architecture.md`가 갱신되었는가?

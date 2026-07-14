# CLAUDE.md

Claude Code가 이 저장소에서 작업할 때 참고하는 가이드입니다. 코드를 작성하기 전에 이 문서와
`docs/architecture.md`, 그리고 현재 작업 중인 마일스톤 문서(`docs/milestones/`)를 먼저 읽으세요.

## 프로젝트 한 줄 요약

FigureMate는 논문의 Figure를 추출하고, 본문과 매칭하고, AI가 근거를 갖춘 설명을 생성하는
파이프라인을 LangGraph Agent로 구성한 백엔드(FastAPI)와 이를 보여주는 프론트엔드(Next.js)로 이루어진다.

```
업로드 → PDF 분석 → Figure 추출 → Figure↔본문 매칭 → Figure별 설명 생성
```

이 5단계가 현재 범위의 전부다. 이 범위를 벗어나는 기능(발표 스크립트, 모의 Q&A, 개인 지식 그래프 등)은
지금 구현하지 않는다. 요청받아도 먼저 `docs/roadmap.md`에 있는지 확인하고, 없으면 범위 밖임을 알린다.

## 현재 상태 (진실 원천: README.md의 "프로젝트 상태" 절)

- ✅ M1~M5 전부 완료 (구조 분석 / Provider Layer / Figure 추출 / 매칭 / 설명 생성 / 뷰어 UI).
- **🎉 MVP 파이프라인 5단계 전체 완결 (2026-07-14).** 백엔드 테스트 65개 통과.
- 🚧 다음: M6 이후 — `docs/roadmap.md`의 방향성 항목에서 사용자가 우선순위를 정하면
  **새 마일스톤 문서를 먼저 작성하고 승인 후 착수한다.**
- 마일스톤 문서는 미리 만들지 않는다 — 직전 마일스톤 DoD 통과 후, 요청받았을 때 작성한다.
- `frontend/`는 M5에서 구현됨 (Next.js 16 App Router + TS + Tailwind v4 — `frontend/AGENTS.md`의
  Next 16 주의사항 참고: params는 Promise, 코드 작성 전 `node_modules/next/dist/docs/` 확인).
  `app/graph/`는 LangGraph 조립됨, `app/agents/`(grounding/explainer)도 구현됨.
- 이 폴더는 아직 git 저장소가 아니다. "커밋" 관련 지시는 git init 후에 유효하다.

## 비용 관련 가드레일 (중요 — 하드 룰)

- **기본 상태에서 유료 API 호출은 불가능해야 한다.** LLM 접근은 반드시
  `app/core/llm/`의 Provider Layer를 경유하고, 기본값은 `LLM_PROVIDER=mock` /
  `EMBEDDING_PROVIDER=mock`(비용 0)이다. mock/ollama(로컬)로 M3~M4를 개발하는 동안
  API 비용이 발생하지 않는다.
- **Anthropic(유료)으로 전환하는 시점에만** `.env`의 `ANTHROPIC_API_KEY`를 확인하고,
  없다면 코드를 실행하기 전에 **사용자에게 먼저 확인**한다 ("키를 발급하고 진행할지,
  보류할지"). 확인 없이 유료 API를 호출하는 코드를 실행하지 않는다.
- Provider를 우회한 직접 SDK 호출(`from anthropic import ...`를 Agent 코드에 쓰는 것 등)을
  추가하지 않는다. 자세한 내용은 `docs/roadmap.md`의 "비용 발생 지점" 절 참고.

## 개발 원칙

1. **마일스톤 순서를 지킨다.** M1 없이 M3을 만들지 않는다. 각 마일스톤은 이전 마일스톤의 산출물을
   입력으로 받는다. 지금 어떤 마일스톤을 작업 중인지 불명확하면 `docs/milestones/`에서 확인한다.
2. **각 마일스톤은 완료 조건(DoD)과 테스트 방법이 명시되어 있다.** 코드를 다 썼다고 끝난 게 아니라,
   해당 마일스톤 문서의 DoD를 충족하는 테스트가 통과해야 완료다.
3. **스키마가 계약이다.** `app/schemas/`에 정의된 Pydantic 모델(Paper, Figure, Match, Explanation)을
   함부로 변경하지 않는다. 변경이 필요하면 이유를 먼저 설명하고 `docs/data-model.md`도 함께 갱신한다.
4. **Agent는 Single Responsibility.** 하나의 Agent 정의를 한 문장으로 말했을 때 "그리고"가 들어가면
   분리를 고려한다. 새 Agent 추가 절차는 `docs/adding-an-agent.md` 참고.
5. **LLM 호출과 결정론적 로직을 구분한다.** PDF 파싱, bbox 좌표 계산, DB 조회 같은 것은 일반 코드로
   처리하고, "의미를 판단해야 하는 것"만 LLM(Provider Layer 경유)에 맡긴다. 모든 것을 프롬프트로 풀지 않는다.
6. **프롬프트는 코드와 분리한다.** 각 Agent 폴더의 `prompt.md`에 시스템 프롬프트를 둔다. 프롬프트
   수정이 Python 코드 diff를 만들지 않도록 한다.
7. **근거 없는 설명을 만들지 않는다.** Figure 설명 생성 시 본문 인용(section/paragraph 참조) 없이
   생성된 설명은 실패로 간주한다. `docs/architecture.md`의 grounding 요구사항을 참고.

## 작업 품질 기준 (모델 무관 하드 룰 — 어떤 모델이 와도 지킨다)

1. **검증 없이 "된다"고 말하지 않는다.** 코드를 고쳤으면 실행해서 확인한 뒤 완료라고
   보고한다. 테스트 통과만으로 부족하면 실서버/브라우저로 실제 시나리오를 돌린다.
   실행 못 했으면 "실행은 못 해봤다"고 명시한다.
2. **Step 체크포인트.** 마일스톤 문서의 Step 하나가 끝날 때마다 멈추고 결과를 보고한 뒤
   확인받고 진행한다. 사용자가 "N~M까지"라고 묶어준 경우에만 연속 진행한다.
3. **채점 기준은 사람이 검수한다.** 골든 케이스(expected 파일)는 채점받을 코드가 스스로
   만들지 않는다 — 초안 + 실제 근거(렌더링, 원문)를 보여주고 승인 후에 테스트를 쓴다.
4. **판정 없이 목록만 제시하지 않는다.** 결과 보고는 항목별로 "정당/오탐" 판정과 근거를
   붙인다. 골든 외 추가 산출물은 전부 하나씩 판정한다.
5. **실측이 추측을 이긴다.** 방식·포맷·임계값 결정은 실제 샘플로 측정한 수치를 먼저
   제시하고, 트레이드오프와 함께 옵션으로 보여준 뒤 사용자가 결정한다.
6. **버그는 재현부터, 증상이 아니라 원인을.** 수정 전에 재현 스크립트/테스트를 만들고
   수정 후 같은 방법으로 확인한다. 워크어라운드로 덮으면 그 사실과 근본 원인을 기록한다.
7. **작업 중 이상 신호와 관찰을 흘려보내지 않는다.** 기대와 다른 값은 본 작업과 무관해
   보여도 원인을 확인하고, "오탐 위험" 같은 관찰은 네거티브 테스트나 문서 note로 남긴다.
8. **결함·한계는 숨기지 않는다.** 미탐·부분 실패도 보고에 포함하고, 마일스톤 완료 시
   "알려진 한계" 절에 항목별로 **다음 단계에 미치는 영향 한 줄**을 붙인다.
9. **구현 중 결정된 정책은 그 자리에서 문서화한다.** "구현 시 결정"으로 열려 있던 것을
   결정하면 `docs/architecture.md`와 마일스톤 문서에 명문화한다. 다음 세션은 기억하지 못한다.
10. **같은 지시를 두 번 이상 반복받으면** 스킬(.claude/skills/)이나 이 파일의 규칙으로
    승격을 제안한다.
11. **보고는 결론 먼저, 수치로.** 실패는 실패라고, 건너뛴 건 건너뛰었다고 쓴다.
12. **모호하면 질문하고, 사용자가 말한 적 없는 선호를 지어내지 않는다.**

## 아키텍처 한눈에 보기

상세는 `docs/architecture.md`. 요약 (✅=구현됨, 🚧=스텁/미구현):

```
frontend (Next.js)       🚧 placeholder (M5)
   │ REST
backend/app/api          ✅ FastAPI 라우트 (papers, figures)
backend/app/graph        🚧 LangGraph 파이프라인 조립 — M3~M4에서 구현
backend/app/agents       🚧 개별 Agent (노드). 폴더 1개 = Agent 1개 — M3~M4에서 구현
backend/app/core         ✅ 설정, DB 세션 등 공통 인프라
backend/app/core/llm     ✅ LLM Provider Layer (mock↔ollama↔anthropic 환경변수 전환)
backend/app/schemas      ✅ Pydantic 모델 (Paper/Section/Paragraph, Figure)
backend/app/services     ✅ 결정론적 로직 (document_parser, figure_extractor, storage)
backend/app/models       ✅ SQLAlchemy ORM (papers, sections, paragraphs, figures)
```

### 파이프라인 → 담당 매핑

| 파이프라인 단계 | 담당 | 종류 | 상태 |
|---|---|---|---|
| PDF 분석 | `document_parser` | 서비스 (결정론적, LLM 미사용) | ✅ M1 |
| Figure 추출 | `figure_extractor` | 서비스 (캡션 앵커 휴리스틱 — LLM 보조 불필요로 실측 종결) | ✅ M2 |
| Figure↔본문 매칭 | `grounding_agent` | Agent (명시 참조 정규식 + 임베딩/LLM 검증) | ✅ M3 |
| Figure 설명 생성 | `explainer_agent` | Agent (Vision + 근거 강제, 타입 판별은 `figure_classifier`) | ✅ M4 |

새 Agent를 추가할 때는 반드시 `docs/adding-an-agent.md`의 체크리스트를 따른다.

## 폴더별 작업 시 주의사항

### `backend/app/agents/<agent_name>/`
각 Agent 폴더는 아래 3개 파일을 기본으로 갖는다:
- `node.py` — LangGraph 노드 함수. 입력/출력은 `schema.py`의 타입을 따른다.
- `prompt.md` — 시스템 프롬프트 (해당되는 경우)
- `schema.py` — 이 Agent의 입출력 Pydantic 모델

`grounding_agent`(M3)가 이 구조의 원본이고 `explainer_agent`(M4)가 그것을 복제해 만든 두 번째
Agent다. 새 Agent는 `docs/adding-an-agent.md` 체크리스트를 따라 이들을 복제해서 시작한다.
공통 패턴: node.py의 진입 함수는 순수 함수(DB 무접촉, Provider 주입 가능), 근거 없는 생성
방지 장치(none_found 강제 등), 골든/단위 테스트 필수.

### `backend/app/core/llm/`
LLM Provider Layer (M1.5). services가 아닌 core에 있는 이유: services는 "결정론적 로직"
폴더이고, Provider는 여러 Agent가 공유하는 횡단 인프라이기 때문 (설정·DB 세션과 같은 계열).
- Agent 코드는 반드시 `get_llm_provider()` / `get_embedding_provider()` 팩토리만 사용한다.
  개별 Provider 모듈을 직접 import하지 않는다 (특정 LLM 종속 금지).
- Anthropic은 임베딩 API가 없다 — 그래서 LLM/임베딩 설정이 분리되어 있다.
- 새 Provider 추가 절차는 `app/core/llm/__init__.py` docstring 참고. 미구현 Provider는
  가짜 스텁 대신 레지스트리에 슬롯만 예약하고 안내 에러를 던진다 (검증 불가능한 코드 금지
  — `docs/milestones/M1.5.md` 참고).

### `backend/app/services/`
- `document_parser`, `figure_extractor`, `figure_classifier`는 **순수 함수**다 (DB/스토리지
  무접촉). LangGraph 노드로 감쌀 때 이 성질에 의존하므로 깨지 않는다.
- `pipeline.py`는 예외 — 순수 함수가 아니라 "순수 함수 호출 + DB 저장 + 상태 전이"를 하는
  stage 함수 모음이다(parse/extract/match/explain/finalize). LangGraph 노드가 이들을 얇게
  감싼다. 로직을 그래프에 이식하지 말고 stage 함수로 유지한다(M4.md Step 6 결정).
- 스토리지 URI는 `local://<상대경로>` 스킴이다 (`storage.py`). S3 전환 시 스킴만 추가한다.

### `backend/app/graph/` (M4에서 구현됨)
- `state.py`의 `PipelineState`가 단일 진실 원천. 새 필드는 이 파일만 수정한다. DB 세션은
  상태가 아니라 `config["configurable"]["db"]`로 노드에 전달한다.
- `pipeline_graph.py`가 그래프 조립부: `parse→extract→match→explain→finalize`(실패 조건부
  엣지). 새 단계는 여기에 노드·엣지를 추가한다. 진입점 `run_pipeline`(`pipeline.process_paper`가 호출).

### `backend/tests/`
- 골든 fixture는 `tests/fixtures/sample_papers/`에 있다: `paper{1,2}.pdf` +
  `*.expected.json`(섹션 골든) + `*.figures.expected.json`(Figure 골든, 형식은
  `docs/data-model.md`의 "Figure 골든 케이스 형식" 절). 골든 파일에는 판단 근거를
  `note` 필드로 남긴다.
- 테스트 DB는 `figuremate_test`다 (conftest.py가 사용, `TEST_DATABASE_URL`로 재정의 가능).
  테스트마다 트랜잭션 롤백으로 격리되고, storage는 tmp_path로 우회된다.
- `tests/agents/<agent_name>/`에 각 Agent의 단위 테스트와 골든 케이스를 둔다 (M3부터).
- 새 기능에는 반드시 마일스톤 문서의 "테스트 방법"대로 검증 가능한 테스트를 함께 작성하고,
  네거티브 테스트(오탐 방지)를 골든의 `known_non_figures`/관찰 기록에서 도출한다.

## 완료의 정의 (Definition of Done) — 끝냈다고 말하기 전에 확인

1. 해당 마일스톤 문서의 DoD 체크리스트가 전부 충족되었다.
2. `cd backend && .venv/bin/python -m pytest tests/ -v` **전체**가 통과한다 (신규뿐 아니라
   회귀 포함 — 2026-07-12 기준 35개).
3. 실서버로 E2E를 한 번 확인했다 (uvicorn 기동 → curl로 실제 시나리오 → 종료. 포트 점유
   프로세스가 남아있으면 `lsof -ti :PORT | xargs kill`).
4. 구현 중 결정한 정책·발견한 한계가 문서에 반영되었다 (architecture.md / 마일스톤 문서
   하단 "알려진 한계" / data-model.md 정합).
5. README.md "프로젝트 상태"를 갱신했다 (마일스톤 완료 시).
6. 보고에 실측 수치와 항목별 판정이 포함되어 있다 (작업 품질 기준 4·5·11).

## 로컬 개발 환경 (이 머신의 실제 상태 — README의 일반 안내와 다름)

- **Docker 없음.** PostgreSQL 16은 Homebrew로 설치·운영한다:
  `brew services start postgresql@16`, psql은 `/opt/homebrew/opt/postgresql@16/bin/psql`.
  DB: `figuremate`(개발) / `figuremate_test`(테스트), 유저/비번 `figuremate`/`figuremate`.
- **시스템 Python은 3.9뿐이다.** `backend/.venv`는 uv로 만든 Python 3.12 환경이며,
  activate하지 않고 `backend/` 기준 상대 경로로 직접 실행한다 (`.venv/bin/python`,
  `.venv/bin/uvicorn`, `.venv/bin/alembic`).
- 셸 상태는 턴마다 초기화되므로 명령 전에 `cd backend`가 필요하다.

## 자주 쓰는 명령 (이 환경에서 실제로 동작하는 형태)

```bash
cd backend

# 전체 테스트 (완료 판정 기준)
.venv/bin/python -m pytest tests/ -v

# 특정 영역만
.venv/bin/python -m pytest tests/services/ -v
.venv/bin/python -m pytest tests/agents/grounding_agent -v   # M3부터

# 로컬 서버
.venv/bin/uvicorn app.main:app --reload

# DB 마이그레이션
.venv/bin/alembic revision --autogenerate -m "설명"   # 생성 후 반드시 파일 검토
.venv/bin/alembic upgrade head

# 의존성 재설치
uv pip install -p .venv/bin/python -e ".[dev]"

# Frontend (M5 이후 — 현재 placeholder)
cd frontend && npm run dev
```

## 환경 변수

`backend/.env.example`이 전체 목록의 진실 원천이다. 핵심:
- `LLM_PROVIDER` / `EMBEDDING_PROVIDER` — 기본 `mock`(비용 0). ollama(로컬) / anthropic(유료).
  **키 없이도 전체 테스트와 서버가 동작하는 것이 정상이다.**
- `ANTHROPIC_API_KEY` — `LLM_PROVIDER=anthropic`일 때만 필요.
- `DATABASE_URL` — PostgreSQL 연결 문자열 (기본값이 위 로컬 환경과 일치).
- `STORAGE_BACKEND=local` + `STORAGE_LOCAL_PATH` — M1~M2는 로컬 파일시스템. S3는 이후.

API 키를 코드나 커밋에 절대 포함하지 않는다.

## 지금 무엇부터 해야 하는가

1. `README.md`의 "프로젝트 상태"에서 현재 위치를 확인한다 (이 문서의 "현재 상태" 절이
   낡았을 수 있다 — README가 우선).
2. 다음 마일스톤 문서가 `docs/milestones/`에 없으면, **코드가 아니라 문서 작성부터** 시작해
   사용자 승인을 받는다 (M1/M2와 같은 형식: 목표/범위/Step/DoD/테스트 방법, 그리고 직전
   마일스톤의 "알려진 한계" 절을 반드시 먼저 읽고 반영).
3. 착수 후에는 위 "작업 품질 기준"의 Step 체크포인트 규칙(2번)을 따른다.

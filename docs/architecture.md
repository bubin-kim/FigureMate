# FigureMate — 아키텍처

이 문서는 MVP 범위(파이프라인 5단계)의 시스템 구조를 설명합니다. 더 큰 비전(발표 준비, 개인
지식 그래프 등)은 `docs/roadmap.md`에 별도로 정리되어 있으며, 이 문서에는 포함하지 않습니다.

## 1. 전체 그림

```
┌─────────────────────────────────────────────────────────┐
│                 Frontend (Next.js)                       │
│   업로드 UI │ Figure 목록/뷰어 │ 본문 하이라이트 패널     │
└──────────────────────────┬────────────────────────────────┘
                           │ REST (+ 진행상태는 폴링 또는 SSE)
┌──────────────────────────┴────────────────────────────────┐
│               API (FastAPI, backend/app/api)              │
│   POST /papers            — 논문 업로드, 파이프라인 트리거 │
│   GET  /papers/{id}       — 논문/처리 상태 조회            │
│   GET  /papers/{id}/figures        — Figure 목록           │
│   GET  /papers/{id}/figures/{fid}  — Figure 상세 + 설명    │
└──────────────────────────┬────────────────────────────────┘
                           │
┌──────────────────────────┴────────────────────────────────┐
│        LangGraph Pipeline (backend/app/graph)              │
│                                                              │
│  document_parser → figure_extractor → grounding_agent      │
│                                       → explainer_agent     │
│                                                              │
│  (순차 파이프라인. Figure가 여러 개면 grounding_agent부터   │
│   Figure 단위로 병렬 fan-out 가능 — M4에서 결정)            │
└──────────────────────────┬────────────────────────────────┘
                           │
┌──────────────┬───────────┴────────────┬────────────────────┐
│  Storage     │   Database (Postgres)   │  Vector Index       │
│  (S3 호환)   │   papers / figures /    │  (pgvector)         │
│  원본 PDF,   │   sections / matches /  │  본문 청크 임베딩    │
│  Figure 이미지│   explanations          │                     │
└──────────────┴─────────────────────────┴────────────────────┘
```

**프론트엔드 구현 (M5)**: Next.js 16(App Router) + TypeScript + Tailwind v4, `frontend/`.
페이지: 업로드(`/`) → 논문 상세(`/papers/[id]`, upload_status 2.5초 폴링 + 단계별 한글 문구)
→ Figure 상세(`/papers/[id]/figures/[figureId]`, 설명·components·grounding 안내 + 본문 패널).
본문 하이라이트는 **(B) 문단 강조** 방식(M5 Step 0 실측 후 결정 — bbox는 정밀했으나 최소
뷰어 취지 우선): `GET /sections` 텍스트를 표시하고 매칭 문단을 배경색 강조, 첫 매칭으로 자동
스크롤. 타입은 `frontend/lib/api.ts`가 백엔드 Pydantic 스키마와 수동 동기화(Literal 값 대조
완료). 백엔드에 CORS(localhost:3000) 추가됨. 상태 폴링은 REST 폴링으로 시작(다이어그램의
SSE는 미도입 — 필요 시 이후 마일스톤).

## 2. 파이프라인 5단계 상세

### 2.1 PDF 분석 (`document_parser`, M1)

**입력**: 업로드된 PDF 파일
**출력**: 구조화된 문서 — 섹션 목록, 각 섹션의 문단(paragraph) 목록, 페이지 레이아웃 정보

**방식**: 결정론적 도구 중심. LLM은 최소한으로만 사용한다.
- PDF 텍스트/레이아웃 추출: PyMuPDF(fitz)
- 섹션 헤딩 탐지: 폰트 크기/굵기 휴리스틱 + 정규식(예: "1. Introduction", "Section 3.2")
- 문단 단위 분할 및 `paragraph_id` 부여 (이후 모든 grounding의 참조 단위)

**왜 여기서 LLM을 쓰지 않는가**: 레이아웃 파싱은 결정론적 문제다. LLM에 맡기면 느리고, 비싸고,
같은 입력에 다른 결과가 나올 수 있다. 애매한 케이스(섹션 헤딩인지 본문인지 불분명)만 필요 시
가벼운 모델로 보조 판별한다.

**Front Matter 정책 (M1에서 결정)**: 첫 헤딩(보통 "Abstract") 이전의 텍스트(제목/저자/소속 등)는
"Front Matter"라는 가상 섹션(order=0)으로 수집한다. 버리면 제목·저자 정보가 유실되고, 임의
섹션에 붙이면 grounding이 오염되므로 명시적인 별도 섹션으로 둔다. 상세는
`backend/app/services/document_parser.py`의 모듈 docstring 참고.

### 2.2 Figure 추출 (`figure_extractor`, M2)

**입력**: M1의 구조화 문서 + 원본 PDF
**출력**: Figure 이미지(크롭된 PNG) + 캡션 텍스트 + 페이지/좌표 정보 목록

**방식** (M2 실측 후 확정 — 상세는 `backend/app/services/figure_extractor.py` docstring):
- **캡션 앵커 파이프라인**: "Figure N" + 구두점(':' 또는 '.') 패턴의 캡션이 Figure의
  개수/정체성을 정의하고, 캡션 위쪽 구역(컬럼 폭 × barrier까지)의 그래픽 요소(임베디드
  이미지 + 벡터 드로잉 클러스터)와 내부 텍스트의 합집합으로 bbox를 결정한다.
  실측 근거: 샘플 12개 Figure 중 임베디드 래스터는 3개뿐이라 렌더링-크롭이 주 경로.
  - **무구두점 캡션 확장 (2026-07-14)**: Springer 계열의 "Fig. 5 A window of 2048 samples"
    스타일(번호 뒤 구두점 없음)은 사용자 논문에서 Figure 0개 추출로 실제 발견되어 지원
    추가. 가짜 캡션 본문("Fig. 6 (middle) shows...")과의 구분을 위해 (A) 150자 이하
    (실측: 진짜 캡션 31~109자 vs 가짜 216자) + (B) 캡션 위 구역에 그래픽 실존을 함께
    요구한다. grounding_agent의 캡션 제외도 (A) 기준으로 동기화됨.
- 크롭 저장: PNG @200dpi (선화/플롯 위주라 JPEG 이득이 적고 M4 Vision 입력 품질 우선 —
  사용자 결정). 단일 래스터가 영역을 덮으면 원본 해상도 바이트를 그대로 저장.
- **처리 시점 (M2에서 결정)**: `POST /papers` 동기 흐름에 포함. 실측 전체 처리(파싱+추출)가
  최악 1.3초로 M1의 "수 초 내" 기준 안이며, 비동기 전환은 LLM이 붙는 M3~M4에서 재설계.
  M1 산출물(섹션/문단)은 Figure 추출 전에 커밋되어 추출이 실패해도 보존된다 (5절 정책).
- LLM 보조 판별: 두 샘플 논문에서 필요 케이스가 발견되지 않아 M2에서는 미도입
  (M2.md의 방침대로 발견 시 사용자 확인 후 도입).

### 2.3 Figure ↔ 본문 매칭 (`grounding_agent`, M3)

**입력**: Figure(캡션 포함) + M1의 전체 문단 목록
**출력**: 각 Figure에 대해 "이 Figure를 설명/참조하는 문단" 목록 (관련도 점수 포함)

**방식 (2단계, M3 실측 후 확정 — 상세는 `grounding_agent/node.py` docstring)**:
1. 명시적 참조 탐지 (결정론): 본문에서 "Figure 2", "Fig. 2" 패턴을 정규식으로 찾아 직접
   연결. score=1.0, quote_span 기록. 캡션 문단 자신은 제외.
2. 의미적 매칭 (Provider Layer 경유): 캡션↔문단 임베딩 코사인 유사도로 후보 선정
   (top-20 AND ≥0.65), 후보를 LLM으로 "이 문단이 이 Figure를 설명하는가" 검증.
   - **후보 필터(A)**: 서지 항목·Table 캡션·80자 미만 문단은 후보에서 제외 (오탐 원천 제거).
   - **인용 게이트(B, 완화)**: LLM이 지어낸 인용(원문에 없는 문구)만 거부. 패러프레이즈는 허용.
   - `extraction_confidence<0.5`인 Figure는 semantic 점수에 상한을 씌워 불확실성을 전파.

**검증 모델 (M3 확정)**: llama3.2(3B)는 관련성 오판이 잦아 qwen2.5:7b로 확정
(EMBEDDING_PROVIDER=ollama/nomic-embed-text + LLM_PROVIDER=ollama/qwen2.5:7b). 기본값 mock은
비용 0이나 의미 유사도가 없어 명시 참조만 산출된다(테스트용). pgvector는 미도입 —
문단 규모(논문당 170~360개)에서 in-process 코사인으로 충분(M3.md 결정 #2).

**처리 시점 (M3에서 비동기로 전환)**: 매칭이 LLM 검증 때문에 논문당 수 분 걸려(실측 662s/2편)
동기 처리가 불가능하다. `POST /papers`는 파일 저장 + Paper(parsing) 생성 후 즉시 응답하고,
parse→figure→matching 파이프라인은 FastAPI BackgroundTasks로 실행한다. 클라이언트는
`GET /papers/{id}`의 upload_status를 폴링한다. 오케스트레이터는 `services/pipeline.py`이며,
M4에서 LangGraph 그래프로 대체된다(M3.md 결정 #3).

이 결과가 이후 "Figure별 설명 생성"의 근거(citation) 자료가 된다.

### 2.4 Figure별 설명 생성 (`explainer_agent`, M4)

**입력**: Figure 이미지 + 캡션 + 매칭된 본문 문단들
**출력**: 근거를 포함한 Figure 설명 (구조화된 텍스트)

**방식** (M4 실측 후 확정 — 상세는 `explainer_agent/node.py`·`prompt.md`):
- Vision Provider(Provider Layer 경유)가 Figure 이미지 + 캡션 + M3 매칭 근거 문단 +
  figure_type을 받아 구조화된 JSON 설명을 생성한다. figure_type은 `figure_classifier`
  (캡션 키워드, Vision 호출 없음)가 판별하며, architecture형은 `ExplanationComponent`로 분해한다.
- **grounding 강제 (코드 레벨)**: 모델이 매칭에 없는 paragraph_id를 근거로 대면 버리고,
  근거가 없으면 `source="none_found"` + 안내 note를 강제한다. 근거 없는 설명이 근거 있는 것처럼
  저장되는 것을 코드가 막는다 (환각 방지 — M3의 "확신 없으면 no"와 같은 계열의 안전장치).
- **모델**: 기본 mock은 구조 검증용(각 Agent가 파싱 가능한 결정론적 JSON 더미). 실품질은
  ollama의 **qwen2.5vl:7b**(무비용) — M4에서 3b로 확정했으나 2026-07-14 실측으로 승격
  (3b: 확률적 JSON 파싱 실패·영어/한자 혼입 잦음, 7b: 어려운 케이스 4/4 첫 시도 성공·깨끗한
  한국어, 대가는 warm ~20초/Figure로 3b의 ~3배). 설명 출력 언어는 한국어(prompt.md).
  Anthropic Vision 전환은 사람이 필요 시 결정(가드레일).
- **생성 견고화 (2026-07-14)**: explain 재시도는 전송·파싱·품질 실패를 합산 3회 상한의 단일
  루프로 처리하고, 재시도마다 temperature를 올린다(0.0→0.4→0.7 — temp=0 불량 모드 탈출.
  깨진 JSON뿐 아니라 그림 라벨의 중국어 번역(siren→汽笛), 키릴 혼입("다иск리트")도 같은 패턴).
  품질 우선순위: 깨끗한 한국어(문체 게이트 통과) > 문체 미달 한국어 > 영어 > 설명 없음(failed).
  깨진 원문은 저장하지 않는다.
- **설명 문체 표준 = 합쇼체(존댓말) (2026-07-14)**: 모든 문장이 "~니다"로 끝나야 게이트를
  통과한다(`pipeline._polite_korean`). '-다'체가 아니라 합쇼체를 표준으로 정한 근거(실측):
  qwen2.5vl:7b는 특정 Figure에서 '-다'체 지시를 3회 재시도 전부 무시할 만큼 합쇼체 성향이
  강했고, 표준을 뒤집자 같은 Figure들이 temp=0 첫 시도에 통과했다. 상세 설명 구조(무엇을
  보여주는가→읽는 법→관찰→의미)와 문체 규칙은 explainer_agent/prompt.md가 정본.
- **처리**: M3의 비동기 파이프라인에 explain 단계로 편입. 개별 Figure 설명 실패는 그 Figure만
  status="failed"로 표시하고 나머지는 계속 (부분 실패 정책).

## 3. Grounding 요구사항 (전체 파이프라인 공통 원칙)

Figure 설명은 반드시 아래 중 하나 이상의 근거를 가져야 한다:
- 매칭된 본문 문단의 `paragraph_id`
- Figure 자체의 캡션

근거가 없는 문장은 MVP 단계에서는 생성하지 않는 것을 원칙으로 한다(모델이 "본문에 명시되지 않음"을
말할 수 있게 프롬프트를 설계한다). 이는 v2/v3 설계 문서의 grounding 원칙을 MVP 규모로 가져온 것이다.

## 4. 왜 LangGraph인가 (MVP 단계에서)

현재 파이프라인은 사실 순차 실행(A→B→C→D)에 가깝다. 그런데도 LangGraph를 쓰는 이유:

1. **상태 공유가 명시적이다.** `PipelineState`가 각 단계의 입출력을 강제하므로, 다음 마일스톤에서
   Figure 단위 병렬 처리나 재시도 로직을 추가할 때 그래프 구조만 바꾸면 된다.
2. **부분 실패를 허용하기 쉽다.** Figure 10개 중 2개의 vision 분석이 실패해도 나머지는 저장하고
   진행하는 정책을 조건부 엣지로 표현할 수 있다.
3. **확장 경로가 코드 레벨에서 보인다.** M6 이후(발표 준비 등)에 새 노드를 추가할 때, 기존 4단계
   그래프에 엣지를 하나 더 붙이는 방식으로 확장한다. 처음부터 함수 체인으로 짰다면 이 확장이
   리팩터링을 요구했을 것이다.

과도한 엔지니어링을 피하기 위해, MVP의 그래프는 **조건부 분기 없이 선형에 가깝게** 시작하고,
필요해질 때 확장한다.

**구현 (M4 Step 6)**: `app/graph/`에 `StateGraph`로 조립됨.
`START → parse → (실패?END) → extract → (실패?END) → match → explain → finalize → END`.
앞 3단계(M1~M3)는 `services/pipeline.py`의 stage 함수를 노드로 감싸기만 하고(로직 재작성 아님),
explain은 Figure들을 순차 처리하는 단일 노드다. explain의 Send fan-out은 실측 후 도입하지
않았다(sync 무이득 + 세션 재진입 + 로컬 GPU 무이득 — `docs/milestones/M4.md` "설계 결정 사후
기록"). 진짜 병렬(Figure별 fan-out)은 async + 서버측 동시성 Provider로의 확장 여지로 남긴다.

## 4.5 LLM Provider Layer (`backend/app/core/llm/`)

FigureMate는 특정 LLM에 종속되지 않는다. M3/M4의 Agent는 `LLMProvider` /
`EmbeddingProvider` 인터페이스만 사용하고, 실제 Provider는 환경변수로 선택한다:

```
LLM_PROVIDER=mock(기본) | ollama | anthropic | openai(슬롯 예약)
EMBEDDING_PROVIDER=mock(기본) | ollama
```

| Provider | complete | embed | vision | 비용 |
|---|---|---|---|---|
| Mock (기본) | 결정론적 더미 | 해시 시드 768차원 단위 벡터 | ✓ | 0 |
| Ollama | localhost HTTP | ✓ (nomic-embed-text) | 모델에 따라 | 0 (로컬) |
| Anthropic (optional) | Claude API | ✗ (임베딩 API 없음) | ✓ | 유료, 키 필수 |

설계 결정:
- **LLM/임베딩 설정 분리**: Anthropic은 임베딩 API가 없으므로 단일 스위치면 전환 약속이
  깨진다. 분리하면 LLM=anthropic + 임베딩=ollama 조합이 가능하다.
- **비용 가드레일** (CLAUDE.md와 연결): 기본값 mock = `.env` 무설정 시 유료 호출 0.
  AnthropicProvider는 생성 시점에 키를 검증해 즉시 실패한다. 테스트는 전부 mock 또는
  httpx 모의 전송으로 네트워크 없이 실행된다.
- `CompletionResponse.model`은 `FigureExplanation.model_used`에 기록된다 (data-model.md).
- 새 Provider 추가 절차는 `app/core/llm/__init__.py` docstring 참고.

## 5. 에러 처리 정책 (MVP 기준)

- PDF 파싱 실패 → 사용자에게 명확한 오류 메시지, 파이프라인 중단
  - HTTP 표현 (M1에서 결정, M3에서 비동기로 갱신): `POST /papers`는 파일 저장 후 즉시
    **200 + `upload_status="parsing"`**으로 응답하고 파이프라인은 백그라운드로 실행된다.
    파싱/추출 실패는 백그라운드에서 `upload_status="failed"` + `error_message`로 전이하며,
    클라이언트는 `GET /papers/{id}`의 `upload_status`를 폴링해 판단한다. 실패는 HTTP 에러가
    아니라 Paper 리소스의 상태로 표현한다. (요청 자체가 잘못된 경우 — 비PDF·빈 파일 — 만
    POST에서 422로 즉시 거부한다.) 실측(2026-07-13): POST 응답 ~29ms.
- 특정 Figure의 매칭 실패 → 해당 Figure만 건너뛰고 나머지는 계속 (부분 성공 허용,
  per-figure try/except). 파싱 실패는 파이프라인 전체 중단, Figure 추출 실패는 섹션/문단
  보존 후 중단.
- **서버 재시작 시 처리 중이던 논문은 비종단 상태(matching/explaining 등)에 고아로 남는다**
  (FastAPI BackgroundTasks는 프로세스와 함께 죽음 — 2026-07-14 실제 발생). 자동 재개는
  없으며, `explain_stage`는 멱등(기존 설명 스킵)이라 수동 재실행으로 재개 가능. 자동 복구
  (기동 시 고아 스캔 등)는 필요해지면 이후 마일스톤에서 — 현재는 로컬 단일 사용자라 수용.
- LLM 호출 실패(타임아웃, 레이트리밋) → 지수 백오프로 최대 3회 재시도 후 실패 처리
  (M5에서 구현: `pipeline._retry_llm` — E2E에서 Vision 호출의 transient 타임아웃이 실제
  관찰되어 explain 단계에 적용. 매칭 단계는 실패 사례 관찰 시 동일 헬퍼로 확장)

## 6. 다음 단계와의 경계

이 문서는 M1~M5(파이프라인 + 최소 뷰어)까지만 다룹니다. 발표 스크립트 생성, 예상 질문, 대화형
Q&A, 개인 학습 이력 등은 `docs/roadmap.md`에서 "M6 이후"로 별도 계획하며, 이 아키텍처의 확장으로
다룹니다 (`explainer_agent`의 출력을 재료로 삼는 새 Agent 추가 패턴).

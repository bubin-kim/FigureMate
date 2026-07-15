# FigureMate

**Figure를 중심으로 논문을 이해하고, 발표와 연구까지 이어주는 AI 학습 플랫폼**

> 논문을 읽는 사람들은 대부분 Figure와 수식에서 막힙니다.
> FigureMate는 Figure를 논문의 핵심 진입점으로 삼아, 이해 → 발표 준비까지 돕습니다.

---

## 무엇을 만드는가

FigureMate는 논문 요약 서비스가 아닙니다. **Figure를 완전히 이해시키는 것**이 목표입니다.

```
논문 업로드
   ↓
PDF 분석          — 텍스트/섹션/Figure 위치를 구조화
   ↓
Figure 추출        — 논문에서 Figure 이미지와 캡션을 분리
   ↓
Figure ↔ 본문 매칭  — 각 Figure를 설명하는 문단을 찾아 연결
   ↓
AI가 Figure별 설명 생성 — 근거(본문 인용)를 갖춘 이해하기 쉬운 설명
```

이 5단계가 MVP의 전부입니다. 여기까지 안정적으로 동작하게 만드는 것이 1차 목표이며,
그 위에 발표 준비, 예상 질문, 대화형 학습 등은 이후 단계에서 확장합니다.

## 왜 만드는가

기존 논문 AI 도구(ChatPDF, SciSpace 등)는 텍스트를 빠르게 요약하는 데 강합니다.
하지만 논문의 핵심 아이디어는 대부분 **Figure**(모델 구조도, 실험 결과 그래프)에 압축되어 있고,
정작 사람들이 막히는 지점은 텍스트가 아니라 Figure입니다.

FigureMate는 "Figure를 설명할 수 있는가"를 이해의 기준으로 삼습니다.

## 기술 스택

| 영역 | 선택 | 비고 |
|---|---|---|
| Backend | Python 3.11+, FastAPI | API 서버 |
| Agent Orchestration | LangGraph | Figure 분석 파이프라인을 Agent 그래프로 구성 |
| LLM | Claude (Anthropic API) | Vision + 텍스트 추론 |
| DB | PostgreSQL | 논문/Figure 메타데이터, 매칭 인덱스 |
| Vector Search | pgvector | 본문 청크 임베딩 검색 |
| Storage | S3 호환 오브젝트 스토리지 | PDF 원본, Figure 이미지 |
| Frontend | Next.js (App Router), TypeScript | PDF 뷰어 + Figure 인터랙티브 뷰 |

## 빠른 시작

> 아직 초기 스캐폴딩 단계입니다. 아래는 목표 형태이며, 실제 명령은 각 모듈이 구현되며 채워집니다.

```bash
# Backend
cd backend
cp .env.example .env        # ANTHROPIC_API_KEY 등 설정
pip install -e ".[dev]"
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## 문서 안내

| 문서 | 용도 |
|---|---|
| [`CLAUDE.md`](./CLAUDE.md) | Claude Code가 이 프로젝트에서 작업할 때 따르는 규칙과 아키텍처 요약 |
| [`docs/architecture.md`](./docs/architecture.md) | 전체 시스템 아키텍처, 파이프라인 상세 |
| [`docs/data-model.md`](./docs/data-model.md) | Figure/Paper/매칭 데이터 스키마 |
| [`docs/milestones/M1.md`](./docs/milestones/M1.md) | 첫 마일스톤 상세 작업지시서 (바로 착수하는 단계) |
| [`docs/adding-an-agent.md`](./docs/adding-an-agent.md) | 새 Agent를 추가하는 절차 |

## 개발 순서 (마일스톤 개요)

MVP 파이프라인 5단계를 그대로 마일스톤화합니다. 각 마일스톤은 독립적으로 테스트 가능합니다.

1. **M1 — PDF 업로드 & 구조 분석**: PDF를 받아 섹션 텍스트로 구조화 ([상세](./docs/milestones/M1.md))
2. **M2 — Figure 추출**: PDF에서 Figure 이미지 + 캡션 크롭
3. **M3 — Figure ↔ 본문 매칭**: 각 Figure를 설명하는 본문 문단 인덱싱
4. **M4 — Figure 설명 생성 (LangGraph)**: Vision 모델로 Figure를 분석하고 근거 있는 설명 생성
5. **M5 — 최소 뷰어 UI**: 업로드 → Figure 목록 → 클릭 시 설명 + 본문 하이라이트

M6 이후(발표 스크립트, 예상 질문, 대화형 Q&A 등)는 M5 완료 후 별도 로드맵 문서에서 계획합니다.

## 프로젝트 상태

✅ **M1 완료 (2026-07-12)** — PDF 업로드 & 구조 분석. 업로드 API(`POST /papers`),
PyMuPDF 기반 섹션/문단 구조화(`document_parser`), PostgreSQL 저장, 골든 케이스
테스트(샘플 논문 2편, 섹션 재현율 100%) 및 API E2E 테스트 통과.
알려진 한계(표 행의 문단 흡수, 번호 없는 부록 헤딩 미탐)는
[`docs/milestones/M1.md`](./docs/milestones/M1.md) 하단 참고.

✅ **M2 완료 (2026-07-12)** — Figure 추출. 캡션 앵커 파이프라인(`figure_extractor`)으로
샘플 2편의 Figure 12개 전부 추출(재현율 100%, 표 오탐 0건). 임베디드 래스터는 원본
해상도로, 벡터 그래픽(12개 중 9개)은 PNG@200dpi 렌더링-크롭으로 저장.
`GET /papers/{id}/figures` 및 이미지 파일 API 제공. 전체 처리(파싱+추출)는 동기,
최악 1.5초. 테스트 21개 통과. 알려진 한계(캡션이 그림 위인 레이아웃, 번호 없는 그림
미탐 — M3 매칭 대상에서 누락됨)는 [`docs/milestones/M2.md`](./docs/milestones/M2.md)
하단 참고.

✅ **M1.5 완료 (2026-07-12)** — LLM Provider Layer. `LLM_PROVIDER`/`EMBEDDING_PROVIDER`
환경변수로 mock(기본, 비용 0)↔ollama(로컬)↔anthropic(유료, optional) 전환.
설계 결정 기록은 [`docs/milestones/M1.5.md`](./docs/milestones/M1.5.md) 참고.

✅ **M3 완료 (2026-07-13)** — Figure ↔ 본문 매칭(`grounding_agent`, 첫 Agent). 1단계 명시
참조 탐지(정규식, 재현율 100%) + 2단계 의미 매칭(nomic-embed-text 임베딩 + qwen2.5:7b LLM
검증, 후보 필터·인용 게이트로 오탐 억제). LLM 검증 때문에 처리가 논문당 수 분 걸려
**POST /papers를 비동기로 전환**(즉시 응답 ~29ms, 완료는 `GET /papers/{id}` 폴링).
`GET /papers/{id}/figures/{fid}/matches` 제공. 알려진 한계(임베딩 재현율 — M2의 "인덱스 누락"과
같은 계열)는 [`docs/milestones/M3.md`](./docs/milestones/M3.md) 하단 참고.

✅ **M4 완료 (2026-07-13)** — Figure 설명 생성(`explainer_agent`, Vision). 타입 판별
(`figure_classifier`, 캡션 키워드) → Vision 설명 생성(qwen2.5vl:7b, 한국어) → 근거 연결.
**핵심: 근거 없는 Figure는 지어내지 않고 `none_found`로 정직하게 표시**(코드 레벨 강제, 환각 차단).
전체 파이프라인을 **LangGraph `StateGraph`로 재조립**(parse→extract→match→explain→finalize).
`GET /papers/{id}/figures/{fid}`에 설명 포함. mock으로 구조 검증(비용 0), 실품질은 ollama로 확인.
알려진 한계·설계 결정은 [`docs/milestones/M4.md`](./docs/milestones/M4.md) 하단 참고.

✅ **M5 완료 (2026-07-14)** — 최소 뷰어 UI (Next.js 16 + TypeScript + Tailwind v4).
업로드 → 처리 단계 폴링(한글 문구) → Figure 목록 → 상세(AI 설명·구성요소·근거 안내) →
본문 문단 강조(하이라이트 방식 B — Step 0 실측 후 결정)까지 브라우저에서 완결.
ollama 실데이터 E2E를 단일 세션으로 검증(논문 1편 ~8.5분, mock이면 수 초).
이 과정에서 발견된 Vision transient 실패는 재시도 정책(`_retry_llm`) 구현으로 해소.
알려진 한계는 [`docs/milestones/M5.md`](./docs/milestones/M5.md) 하단 참고.

**🎉 MVP 파이프라인 5단계 전체 완결 — 업로드 → PDF 분석 → Figure 추출 → 매칭 → 설명 생성
→ 뷰어 UI.** README가 처음 정의한 MVP 범위가 전부 동작한다. 백엔드 테스트 78개 통과.

✅ **post-MVP 개선 (2026-07-14~15)**:
- **느슨한 캡션 규칙** — 구두점 없는 Springer 스타일 캡션("Fig. N 텍스트") 지원
  (길이 ≤150자 + 캡션 위 그래픽 존재 검증의 A+B 조합, 가짜 캡션 오탐 차단 유지).
- **Vision 모델 qwen2.5vl:3b → 7b 승격** — 어려운 케이스 4/4 첫 시도 파싱·깨끗한 한국어
  (대가: Figure당 ~20초, 3b의 ~3배). 실측 비교는 architecture.md 2.4.
- **한국어 설명 + 품질 게이트** — 상세 설명 구조화(읽는 법→관찰→의미), 문체 표준
  합쇼체(존댓말), 외국 문자(한자·키릴) 혼입 차단, 온도 상승 재시도(0.0→0.4→0.7).
- **홈 화면 논문 히스토리** — `GET /papers`(최신순, Figure 수 포함) + "지난 논문 다시 보기" UI.
- **처리 화면 개선** — 단계별 예상 시간, 경과 카운터, 스피너.

🚧 다음: M6 이후 — [`docs/roadmap.md`](./docs/roadmap.md)의 방향성 항목(대화형 Q&A, 발표
스크립트, 예상 질문 등)에서 우선순위를 정해 새 마일스톤 문서를 작성하고 착수.
배포(Streamlit 데모 등)는 보류 상태 (2026-07-15 사용자 결정).

## 라이선스

TBD

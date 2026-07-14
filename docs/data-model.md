# FigureMate — 데이터 모델

파이프라인 각 단계의 입출력 스키마입니다. `backend/app/schemas/`의 Pydantic 모델과 1:1로
대응해야 하며, 스키마 변경 시 이 문서도 함께 갱신합니다.

## 개체 관계 개요

```
Paper (1) ──< (N) Section ──< (N) Paragraph
  │
  └──< (N) Figure ──< (N) FigureTextMatch >── (N) Paragraph
              │
              └── (1) FigureExplanation
```

## Paper

```python
class Paper(BaseModel):
    id: UUID
    title: str | None            # 추출 실패 시 None 허용, 파일명으로 대체
    filename: str
    upload_status: Literal["uploaded", "parsing", "extracting_figures",
                            "matching", "explaining", "done", "failed"]
    page_count: int
    created_at: datetime
    error_message: str | None    # failed 상태일 때 사유

class PaperListItem(Paper):     # GET /papers 목록 응답 (홈 화면 히스토리, 최신순)
    figure_count: int            # 추출된 Figure 수 — 목록에서 "Figure N개" 표시용
```

## Section / Paragraph (M1 산출물)

```python
class Section(BaseModel):
    id: UUID
    paper_id: UUID
    title: str                   # 예: "3.2 Model Architecture"
    order: int                   # 논문 내 등장 순서
    page_start: int
    page_end: int

class Paragraph(BaseModel):
    id: UUID                     # ★grounding의 참조 단위 — 다른 모든 매칭이 이 id를 가리킨다
    section_id: UUID
    paper_id: UUID
    text: str
    order: int                   # 섹션 내 순서
    page: int
    bbox: list[float] | None     # [x0, y0, x1, y1], 하이라이트 UI용 (있으면 사용)
```

## Figure (M2 산출물)

```python
class Figure(BaseModel):
    id: UUID
    paper_id: UUID
    figure_number: str            # 캡션에서 추출한 번호, 예: "Figure 1" (탐지 실패 시 "Figure ?N")
    caption: str
    image_uri: str                 # 저장소 경로 (S3 등)
    page: int
    bbox: list[float]              # 원본 PDF 페이지 내 좌표
    extraction_confidence: float   # 0~1, 캡션-이미지 매칭 신뢰도
    status: Literal["extracted", "matching", "explained", "failed"]
```

### Figure 골든 케이스 형식 (M2 테스트 fixture)

`tests/fixtures/sample_papers/<paper>.figures.expected.json`. M1의 섹션 골든 케이스와 같은
철학(사람 검수 + 판단 근거를 파일 안에 기록)을 따르며, M2 Step 0에서 형식이 확정되었다.

```json
{
  "paper": "논문 식별 정보",
  "note": "판단 근거 기록 (검증 방법, 래스터/벡터 구성, 캡션 판별 규칙 등)",
  "figures": [
    {"figure_number": "Figure 1", "page": 3, "caption_contains": "캡션의 고유한 부분 문자열"}
  ],
  "known_non_figures": [
    {"pattern": "Table 1", "page": 6, "why": "표 — Figure로 오탐 금지"}
  ]
}
```

- `figures`: 재현율 채점 대상 (기준 ≥90%).
- `known_non_figures`: **오탐 네거티브 테스트 대상.** 추출 결과에 이 항목이 Figure로 포함되면
  실패로 간주한다. 표(Table), 캡션처럼 보이는 본문 문장("Table 2 summarizes...") 등
  실측에서 발견된 오탐 위험 케이스를 기록한다.

## FigureTextMatch (M3 산출물)

Figure 하나당 여러 매칭 문단을 가질 수 있으므로 별도 테이블로 분리합니다.

```python
class FigureTextMatch(BaseModel):
    id: UUID
    figure_id: UUID
    paragraph_id: UUID
    match_type: Literal["explicit_reference", "semantic_similarity"]
    # explicit_reference: 본문에 "Figure N" 형태로 직접 언급됨 (신�, 높음)
    # semantic_similarity: 임베딩 유사도 기반 후보 (LLM 검증 통과)
    relevance_score: float         # 0~1
    quote_span: tuple[int, int] | None   # paragraph.text 내에서 실제 참조 위치 (explicit인 경우)
```

## FigureExplanation (M4 산출물)

```python
class FigureExplanation(BaseModel):
    id: UUID
    figure_id: UUID
    figure_type: FigureType        # (M4 추가) 프롬프트 분기·UI 표시용. 아래 FigureType 참고
    summary: str                   # 1~2문장 핵심 요약
    detailed_explanation: str      # 본문 형태의 상세 설명
    components: list[ExplanationComponent]  # Figure를 구성 요소 단위로 쪼갠 설명 (선택적, 아키텍처 다이어그램형에 유용)
    grounding: list[GroundingRef]  # ★이 설명이 참조한 근거 목록 (none_found여도 항목으로 남김)
    model_used: str                # 예: "ollama:qwen2.5vl:7b", "mock"
    generated_at: datetime

class ExplanationComponent(BaseModel):
    label: str                     # 예: "STFT", "Mel Filterbank"
    role: str                      # 이 구성요소가 하는 일 (1문장)
    plain_explanation: str         # 쉬운 설명 (비유 포함 가능)
    grounding: list[GroundingRef]

class GroundingRef(BaseModel):
    paragraph_id: UUID | None      # 본문 근거
    source: Literal["paragraph", "caption", "none_found"]
    note: str | None               # "본문에 명시되지 않음, 일반적 정의 사용" 등
```

**중요**: `grounding`이 빈 리스트이고 `source`가 `"none_found"`인 문장이 있다면, 그 사실을
UI에서도 숨기지 않고 "본문에 근거 없음 — 일반 지식" 같은 표시로 보여줍니다. 근거를 조작해서
채우지 않는 것이 이 스키마의 핵심 원칙입니다.

**저장 방식 (M4 구현)**: `figure_explanations` 테이블(Figure와 1:1, figure_id unique).
`components`·`grounding`은 중첩 구조이고 설명 단위로 통째로 읽히므로 JSONB 컬럼에 저장한다
(개별 조회하지 않음). `GroundingRef.paragraph_id`는 JSON 안에 문자열 UUID로 보관되며 FK
강제는 없다 — 근거의 정본은 M3의 `FigureTextMatch`(FK 있음)이고, 여기 grounding은 그것을
가리키는 표시용 스냅샷이다.

## Figure 타입 (M4 프롬프트 분기용, 참고)

MVP에서는 아키텍처 다이어그램형 Figure를 우선 지원합니다. 타입 판별은 러프한 휴리스틱 +
LLM 판단으로 시작하고, 필요 시 확장합니다.

```python
FigureType = Literal[
    "architecture",   # 모델 구조도 — components 분해가 특히 유용
    "plot",            # 그래프/차트 — 축, 경향, 비교가 핵심
    "qualitative",     # 정성적 예시 (샘플 이미지 등)
    "other",
]
```

## 마이그레이션 정책

스키마는 Alembic으로 관리합니다. `Paragraph.id`, `Figure.id`처럼 다른 테이블이 참조하는 ID는
한번 정해지면 타입(UUID)을 변경하지 않습니다. 새 필드 추가는 자유롭게 하되, 기존 필드의 의미를
바꾸는 변경은 이 문서 갱신 + 마이그레이션 가이드를 함께 작성합니다.

// FigureMate 백엔드 API 클라이언트 + 타입.
//
// ★ 아래 타입은 backend/app/schemas/*.py (docs/data-model.md)와 손으로 맞춘 것이다.
//   백엔드 스키마가 바뀌면 이 파일도 함께 갱신해야 한다 (자동 생성 도구는 M5 범위 밖).
//   Literal 유니온은 백엔드 Literal과 값이 정확히 일치해야 한다 (2026-07-13 대조 완료):
//   - UploadStatus    ↔ app/schemas/paper.py       UploadStatus
//   - FigureStatus    ↔ app/schemas/figure.py      FigureStatus
//   - FigureType      ↔ app/schemas/explanation.py FigureType
//   - GroundingSource ↔ app/schemas/explanation.py GroundingSource
//   - MatchType       ↔ app/schemas/match.py       MatchType

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// --- Literal 유니온 (백엔드와 값 일치) ---

export type UploadStatus =
  | "uploaded"
  | "parsing"
  | "extracting_figures"
  | "matching"
  | "explaining"
  | "done"
  | "failed";

export type FigureStatus = "extracted" | "matching" | "explained" | "failed";

export type FigureType = "architecture" | "plot" | "qualitative" | "other";

export type GroundingSource = "paragraph" | "caption" | "none_found";

export type MatchType = "explicit_reference" | "semantic_similarity";

// --- 개체 타입 (Pydantic 모델 대응) ---

export interface Paper {
  id: string;
  title: string | null;
  filename: string;
  upload_status: UploadStatus;
  page_count: number;
  created_at: string; // ISO datetime
  error_message: string | null;
}

// GET /papers 목록 항목 (backend PaperListItem — 홈 히스토리용 figure 수 포함)
export interface PaperListItem extends Paper {
  figure_count: number;
}

export interface Paragraph {
  id: string;
  section_id: string;
  paper_id: string;
  text: string;
  order: number;
  page: number;
  bbox: number[] | null;
}

export interface Section {
  id: string;
  paper_id: string;
  title: string;
  order: number;
  page_start: number;
  page_end: number;
}

export interface SectionWithParagraphs extends Section {
  paragraphs: Paragraph[];
}

export interface Figure {
  id: string;
  paper_id: string;
  figure_number: string;
  caption: string;
  image_uri: string;
  page: number;
  bbox: number[];
  extraction_confidence: number;
  status: FigureStatus;
}

export interface GroundingRef {
  paragraph_id: string | null;
  source: GroundingSource;
  note: string | null;
}

export interface ExplanationComponent {
  label: string;
  role: string;
  plain_explanation: string;
  grounding: GroundingRef[];
}

export interface FigureExplanation {
  id: string;
  figure_id: string;
  figure_type: FigureType;
  summary: string;
  detailed_explanation: string;
  components: ExplanationComponent[];
  grounding: GroundingRef[];
  model_used: string;
  generated_at: string; // ISO datetime
}

export interface FigureDetail extends Figure {
  explanation: FigureExplanation | null;
}

export interface FigureTextMatch {
  id: string;
  figure_id: string;
  paragraph_id: string;
  match_type: MatchType;
  relevance_score: number;
  quote_span: [number, number] | null;
  paragraph_text: string;
  paragraph_page: number;
}

// --- fetch 래퍼 ---

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} 실패: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// --- API 함수 (docs/milestones/M5.md Step 2) ---

export async function uploadPaper(file: File): Promise<Paper> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/papers`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    throw new Error(`업로드 실패: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<Paper>;
}

export const getPaper = (id: string) => getJson<Paper>(`/papers/${id}`);

export const listPapers = () => getJson<PaperListItem[]>("/papers");

export const getPaperSections = (id: string) =>
  getJson<SectionWithParagraphs[]>(`/papers/${id}/sections`);

export const getFigures = (paperId: string) =>
  getJson<Figure[]>(`/papers/${paperId}/figures`);

export const getFigure = (paperId: string, figureId: string) =>
  getJson<FigureDetail>(`/papers/${paperId}/figures/${figureId}`);

export const getFigureMatches = (paperId: string, figureId: string) =>
  getJson<FigureTextMatch[]>(`/papers/${paperId}/figures/${figureId}/matches`);

// <img src>용 이미지 URL (fetch 아님 — 태그에 직접 넣는다)
export const figureImageUrl = (paperId: string, figureId: string) =>
  `${API_BASE}/papers/${paperId}/figures/${figureId}/image`;

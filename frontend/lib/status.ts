// upload_status → 사람이 읽는 한글 문구 + 단계 진행 표시용 유틸.
// 값은 lib/api.ts의 UploadStatus(=백엔드 Literal)와 일치.

import type { UploadStatus } from "./api";

export const STATUS_LABEL: Record<UploadStatus, string> = {
  uploaded: "업로드됨",
  parsing: "본문을 분석하고 있어요",
  extracting_figures: "Figure를 찾고 있어요",
  matching: "Figure와 본문을 연결하고 있어요",
  explaining: "AI가 Figure를 설명하고 있어요",
  done: "완료",
  failed: "실패",
};

// 처리 진행 단계 순서 (진행률 표시용). uploaded/done/failed는 여기 포함하지 않는다.
export const PROCESSING_STAGES: UploadStatus[] = [
  "parsing",
  "extracting_figures",
  "matching",
  "explaining",
];

// 단계별 예상 소요 시간 (ollama 로컬 기준 실측: M3 매칭 ~4.6분, M4 설명 5개 ~4분/9개 ~5분,
// 파싱·추출은 1~2초). LLM_PROVIDER=mock이면 수 초에 끝나므로 이 안내는 상한으로 읽힌다.
export const STAGE_ESTIMATE: Partial<Record<UploadStatus, string>> = {
  parsing: "수 초",
  extracting_figures: "수 초",
  matching: "보통 3~5분",
  explaining: "보통 3~5분",
};

// 전체 예상 안내 문구 (실측: 논문 1편 5~10분, Figure 수에 비례)
export const TOTAL_ESTIMATE_TEXT =
  "전체 보통 5~10분 정도 걸려요 (논문 길이와 Figure 수에 따라 달라져요)";

export function isTerminal(status: UploadStatus): boolean {
  return status === "done" || status === "failed";
}

// 현재 단계가 몇 번째인지 (1-based). 처리 단계가 아니면 0.
export function stageIndex(status: UploadStatus): number {
  const i = PROCESSING_STAGES.indexOf(status);
  return i === -1 ? 0 : i + 1;
}

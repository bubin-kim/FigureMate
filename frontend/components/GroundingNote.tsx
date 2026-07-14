import type { GroundingRef } from "@/lib/api";

// grounding 표시. none_found면 M4가 준비한 note를 "경고"가 아니라 "안내" 톤으로 보여준다
// (M5.md Step 4 요구). paragraph 근거가 있으면 개수만 안내 (실제 본문 연동은 Step 5).
export default function GroundingNote({
  grounding,
}: {
  grounding: GroundingRef[];
}) {
  const noneFound = grounding.filter((g) => g.source === "none_found");
  const paragraphCount = grounding.filter((g) => g.source === "paragraph").length;

  if (noneFound.length > 0) {
    return (
      <div className="flex items-start gap-2 rounded-md bg-sky-50 px-3 py-2 text-sm text-sky-800">
        <span aria-hidden>💡</span>
        <span>
          {noneFound[0].note ?? "이 설명은 일반적인 관찰에 근거합니다."}
        </span>
      </div>
    );
  }

  if (paragraphCount > 0) {
    return (
      <p className="text-xs text-neutral-500">
        본문 근거 {paragraphCount}곳에 연결됨
      </p>
    );
  }

  return null;
}

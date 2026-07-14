"use client";

import { useEffect, useRef, useState } from "react";
import {
  getFigureMatches,
  getPaperSections,
  type SectionWithParagraphs,
} from "@/lib/api";

// 본문 패널 (M5 하이라이트 방식 B): GET /sections 본문을 표시하고, 이 Figure에 매칭된
// 문단을 배경색으로 강조한다. 첫 매칭 문단으로 자동 스크롤한다.
// 매칭이 없으면(none_found) "강조할 문단이 없다"를 명확히 안내한다.
export default function BodyPanel({
  paperId,
  figureId,
}: {
  paperId: string;
  figureId: string;
}) {
  const [sections, setSections] = useState<SectionWithParagraphs[] | null>(null);
  const [matchedIds, setMatchedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const firstMatchRef = useRef<HTMLParagraphElement | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([getPaperSections(paperId), getFigureMatches(paperId, figureId)])
      .then(([secs, matches]) => {
        if (!active) return;
        setSections(secs);
        setMatchedIds(new Set(matches.map((m) => m.paragraph_id)));
      })
      .catch(
        (e) =>
          active &&
          setError(e instanceof Error ? e.message : "본문을 불러오지 못했어요."),
      );
    return () => {
      active = false;
    };
  }, [paperId, figureId]);

  // 첫 매칭 문단으로 스크롤
  useEffect(() => {
    if (matchedIds.size > 0 && firstMatchRef.current) {
      firstMatchRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [sections, matchedIds]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!sections) return <p className="text-sm text-neutral-500">본문 불러오는 중…</p>;

  const hasMatches = matchedIds.size > 0;
  // 첫 매칭 문단 id를 미리 계산 (렌더 중 변수 재할당 없이 ref를 붙이기 위함)
  const firstMatchId = sections
    .flatMap((s) => s.paragraphs)
    .find((p) => matchedIds.has(p.id))?.id;

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold text-neutral-600">본문 근거</h2>

      {hasMatches ? (
        <p className="text-xs text-neutral-500">
          이 Figure와 연결된 본문 {matchedIds.size}곳이 아래에 노란색으로 강조돼 있어요.
        </p>
      ) : (
        <div className="flex items-start gap-2 rounded-md bg-sky-50 px-3 py-2 text-sm text-sky-800">
          <span aria-hidden>💡</span>
          <span>
            이 Figure와 직접 연결된 본문 문단을 찾지 못해, 강조된 부분이 없어요.
            아래는 논문 본문 전체입니다.
          </span>
        </div>
      )}

      <div className="max-h-[60vh] space-y-4 overflow-y-auto rounded-lg border border-neutral-200 p-4">
        {sections.map((sec) => (
          <div key={sec.id} className="space-y-1.5">
            <h3 className="text-sm font-semibold">{sec.title}</h3>
            {sec.paragraphs.map((p) => {
              const matched = matchedIds.has(p.id);
              return (
                <p
                  key={p.id}
                  ref={p.id === firstMatchId ? firstMatchRef : undefined}
                  className={
                    "text-sm leading-relaxed " +
                    (matched
                      ? "rounded bg-yellow-100 px-1.5 py-1 text-neutral-900"
                      : "text-neutral-600")
                  }
                >
                  {p.text}
                </p>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}

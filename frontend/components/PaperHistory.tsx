"use client";

// 홈 화면의 "지난 논문 다시 보기" 목록 — GET /papers (최신순, figure_count 포함).
// 다시 공부하다가 "저번에 봤던 그 논문" 을 찾아 들어가는 진입점.

import Link from "next/link";
import { useEffect, useState } from "react";
import { listPapers, type PaperListItem, type UploadStatus } from "@/lib/api";
import { STATUS_LABEL, isTerminal } from "@/lib/status";

function statusBadgeClass(status: UploadStatus): string {
  if (status === "done") return "bg-neutral-100 text-neutral-600";
  if (status === "failed") return "bg-red-50 text-red-600";
  return "bg-amber-50 text-amber-700"; // 처리 중 단계들
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function PaperHistory() {
  const [papers, setPapers] = useState<PaperListItem[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    listPapers()
      .then(setPapers)
      .catch(() => setError(true));
  }, []);

  if (error) {
    return (
      <p className="text-center text-xs text-neutral-400">
        지난 논문 목록을 불러오지 못했어요. 백엔드 서버가 켜져 있는지 확인해 주세요.
      </p>
    );
  }
  if (papers === null || papers.length === 0) return null;

  return (
    <section className="space-y-3" data-testid="paper-history">
      <h2 className="text-sm font-medium text-neutral-500">
        지난 논문 다시 보기
      </h2>
      <ul className="divide-y divide-neutral-100 rounded-xl border border-neutral-200">
        {papers.map((paper) => (
          <li key={paper.id}>
            <Link
              href={`/papers/${paper.id}`}
              className="flex items-center gap-3 px-4 py-3 hover:bg-neutral-50"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">
                  {paper.title ?? paper.filename}
                </p>
                <p className="mt-0.5 text-xs text-neutral-400">
                  {formatDate(paper.created_at)}
                  {paper.upload_status === "done" &&
                    ` · Figure ${paper.figure_count}개`}
                </p>
              </div>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${statusBadgeClass(paper.upload_status)}`}
              >
                {isTerminal(paper.upload_status)
                  ? STATUS_LABEL[paper.upload_status]
                  : "처리 중"}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

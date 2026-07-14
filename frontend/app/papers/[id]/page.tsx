"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { getPaper, type Paper } from "@/lib/api";
import {
  PROCESSING_STAGES,
  STAGE_ESTIMATE,
  STATUS_LABEL,
  TOTAL_ESTIMATE_TEXT,
  isTerminal,
  stageIndex,
} from "@/lib/status";
import FigureGrid from "@/components/FigureGrid";

const POLL_INTERVAL_MS = 2500;

export default function PaperDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params); // Next 16: params는 Promise
  const [paper, setPaper] = useState<Paper | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const p = await getPaper(id);
        if (!active) return;
        setPaper(p);
        if (!isTerminal(p.upload_status)) {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (e) {
        if (!active) return;
        setError(e instanceof Error ? e.message : "상태를 불러오지 못했어요.");
      }
    }
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [id]);

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-12">
      <Link href="/" className="text-sm text-neutral-500 hover:underline">
        ← 새 논문 업로드
      </Link>

      {error && (
        <p className="mt-8 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}

      {!paper && !error && (
        <p className="mt-8 text-sm text-neutral-500">불러오는 중…</p>
      )}

      {paper && (
        <div className="mt-6 space-y-6">
          <h1 className="text-xl font-semibold">
            {paper.title ?? paper.filename}
          </h1>

          {paper.upload_status === "failed" ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4">
              <p className="text-sm font-medium text-red-700">처리에 실패했어요.</p>
              {paper.error_message && (
                <p className="mt-1 text-sm text-red-600">{paper.error_message}</p>
              )}
              <Link
                href="/"
                className="mt-3 inline-block text-sm font-medium text-red-700 underline"
              >
                다시 시도하기
              </Link>
            </div>
          ) : paper.upload_status === "done" ? (
            <div className="space-y-4">
              <p className="text-sm text-neutral-500">
                {paper.page_count}쪽 · Figure를 눌러 AI 설명과 근거를 확인하세요.
              </p>
              <FigureGrid paperId={paper.id} />
            </div>
          ) : (
            <ProcessingStatus paper={paper} />
          )}
        </div>
      )}
    </main>
  );
}

function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-900"
    />
  );
}

function formatElapsed(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return m > 0 ? `${m}분 ${s}초` : `${s}초`;
}

function ProcessingStatus({ paper }: { paper: Paper }) {
  const status = paper.upload_status;
  const current = stageIndex(status);

  // 경과 시간: created_at 기준 1초마다 갱신 — 카운터가 올라가는 것 자체가
  // "지금 실제로 처리 중"이라는 가장 확실한 신호다 (새로고침해도 정확).
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const elapsedSec = Math.max(
    0,
    Math.floor((now - new Date(paper.created_at).getTime()) / 1000),
  );

  return (
    <div className="rounded-lg border border-neutral-200 p-5">
      <div className="flex items-center gap-3">
        <Spinner />
        <p className="text-sm font-medium" data-testid="current-stage">
          {STATUS_LABEL[status]}
        </p>
      </div>

      <ol className="mt-4 space-y-1.5">
        {PROCESSING_STAGES.map((stage, i) => {
          const n = i + 1;
          const state =
            n < current ? "done" : n === current ? "active" : "todo";
          return (
            <li
              key={stage}
              className={
                "flex items-center gap-2 text-sm " +
                (state === "todo" ? "text-neutral-400" : "text-neutral-700")
              }
            >
              <span className="flex w-4 items-center justify-center">
                {state === "done" ? (
                  "✓"
                ) : state === "active" ? (
                  <Spinner />
                ) : (
                  "·"
                )}
              </span>
              <span>{STATUS_LABEL[stage]}</span>
              {STAGE_ESTIMATE[stage] && (
                <span className="text-xs text-neutral-400">
                  ({STAGE_ESTIMATE[stage]})
                </span>
              )}
            </li>
          );
        })}
      </ol>

      <p className="mt-4 text-xs text-neutral-500">
        경과 <span className="font-medium tabular-nums">{formatElapsed(elapsedSec)}</span>
        {" · "}
        {TOTAL_ESTIMATE_TEXT}
      </p>
    </div>
  );
}

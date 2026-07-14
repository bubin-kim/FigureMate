"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { figureImageUrl, getFigure, type FigureDetail } from "@/lib/api";
import GroundingNote from "@/components/GroundingNote";
import BodyPanel from "@/components/BodyPanel";

export default function FigureDetailPage({
  params,
}: {
  params: Promise<{ id: string; figureId: string }>;
}) {
  const { id, figureId } = use(params);
  const [figure, setFigure] = useState<FigureDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getFigure(id, figureId)
      .then((f) => active && setFigure(f))
      .catch((e) =>
        active &&
        setError(e instanceof Error ? e.message : "Figure를 불러오지 못했어요."),
      );
    return () => {
      active = false;
    };
  }, [id, figureId]);

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-12">
      <Link
        href={`/papers/${id}`}
        className="text-sm text-neutral-500 hover:underline"
      >
        ← Figure 목록
      </Link>

      {error && <p className="mt-8 text-sm text-red-600">{error}</p>}
      {!figure && !error && (
        <p className="mt-8 text-sm text-neutral-500">불러오는 중…</p>
      )}

      {figure && (
        <div className="mt-6 space-y-6">
          <div>
            <h1 className="text-xl font-semibold">{figure.figure_number}</h1>
            <p className="mt-1 text-sm text-neutral-500">{figure.caption}</p>
          </div>

          <div className="flex justify-center overflow-hidden rounded-lg border border-neutral-200 bg-neutral-50 p-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={figureImageUrl(id, figureId)}
              alt={figure.figure_number}
              className="max-h-[28rem] w-auto object-contain"
            />
          </div>

          <Explanation figure={figure} />

          <BodyPanel paperId={id} figureId={figureId} />
        </div>
      )}
    </main>
  );
}

function Explanation({ figure }: { figure: FigureDetail }) {
  const exp = figure.explanation;
  if (!exp) {
    return (
      <p className="text-sm text-neutral-500">
        아직 이 Figure의 설명이 없어요.
      </p>
    );
  }

  return (
    <section className="space-y-5">
      <div className="flex items-center gap-2">
        <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600">
          {exp.figure_type}
        </span>
      </div>

      {exp.summary && (
        <p className="text-base font-medium leading-relaxed">{exp.summary}</p>
      )}

      {exp.detailed_explanation && (
        <p className="whitespace-pre-line text-sm leading-relaxed text-neutral-700">
          {exp.detailed_explanation}
        </p>
      )}

      {/* architecture형: 구성요소 분해를 목록으로 */}
      {exp.components.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-neutral-600">구성 요소</h2>
          <ul className="space-y-3">
            {exp.components.map((c, i) => (
              <li
                key={`${c.label}-${i}`}
                className="rounded-lg border border-neutral-200 p-3"
              >
                <p className="text-sm font-medium">{c.label}</p>
                {c.role && (
                  <p className="mt-0.5 text-xs text-neutral-500">{c.role}</p>
                )}
                {c.plain_explanation && (
                  <p className="mt-1.5 text-sm text-neutral-700">
                    {c.plain_explanation}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <GroundingNote grounding={exp.grounding} />
    </section>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { figureImageUrl, getFigures, type Figure } from "@/lib/api";

export default function FigureGrid({ paperId }: { paperId: string }) {
  const [figures, setFigures] = useState<Figure[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getFigures(paperId)
      .then((f) => active && setFigures(f))
      .catch((e) =>
        active &&
        setError(e instanceof Error ? e.message : "Figure를 불러오지 못했어요."),
      );
    return () => {
      active = false;
    };
  }, [paperId]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!figures) return <p className="text-sm text-neutral-500">Figure 불러오는 중…</p>;
  if (figures.length === 0)
    return <p className="text-sm text-neutral-500">추출된 Figure가 없어요.</p>;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {figures.map((f) => (
        <Link
          key={f.id}
          href={`/papers/${paperId}/figures/${f.id}`}
          className="group flex flex-col gap-2 rounded-lg border border-neutral-200 p-3 transition hover:border-neutral-400"
        >
          <div className="flex items-center justify-center overflow-hidden rounded bg-neutral-50">
            {/* 백엔드가 주는 동적 URL이라 next/image 대신 <img> 사용 (최소 뷰어) */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={figureImageUrl(paperId, f.id)}
              alt={f.figure_number}
              className="max-h-48 w-auto object-contain"
            />
          </div>
          <div>
            <p className="text-sm font-medium">{f.figure_number}</p>
            <p className="line-clamp-2 text-xs text-neutral-500">{f.caption}</p>
          </div>
        </Link>
      ))}
    </div>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import PaperHistory from "@/components/PaperHistory";
import { uploadPaper } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const paper = await uploadPaper(file);
      router.push(`/papers/${paper.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "업로드 중 오류가 발생했어요.");
      setUploading(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-full w-full max-w-xl flex-col justify-center gap-8 px-6 py-16">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">FigureMate</h1>
        <p className="text-sm text-neutral-500">
          논문 PDF를 올리면 Figure를 찾아 AI 설명과 본문 근거를 함께 보여줘요.
        </p>
      </div>

      <div className="space-y-4 rounded-xl border border-neutral-200 p-6">
        <label className="block">
          <span className="mb-2 block text-sm font-medium">논문 PDF</span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setError(null);
            }}
            className="block w-full text-sm text-neutral-600 file:mr-4 file:rounded-md file:border-0 file:bg-neutral-900 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-neutral-700"
          />
        </label>

        {file && (
          <p className="text-xs text-neutral-500">
            선택됨: {file.name} ({Math.round(file.size / 1024)} KB)
          </p>
        )}

        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="w-full rounded-md bg-neutral-900 px-4 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-neutral-300"
        >
          {uploading ? "업로드 중…" : "업로드하고 분석 시작"}
        </button>

        {error && (
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        )}
      </div>

      <p className="text-center text-xs text-neutral-400">
        처리에는 논문 1편당 수 분이 걸릴 수 있어요.
      </p>

      <PaperHistory />
    </main>
  );
}

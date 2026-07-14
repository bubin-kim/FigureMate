# FigureMate — Frontend (M5 최소 뷰어 UI)

Next.js(App Router) + TypeScript + Tailwind CSS v4. 백엔드 API(`localhost:8000`)를 사용해
PDF 업로드 → 처리 상태 폴링 → Figure 목록/설명 → 본문 문단 강조를 보여준다.

상세 작업지시서는 `docs/milestones/M5.md`. 하이라이트 방식은 (B) 문단 강조로 확정(M5 Step 0
결정) — `GET /papers/{id}/sections`의 본문 텍스트를 표시하고 매칭된 문단을 배경색으로 강조한다.

## 개발

```bash
npm install
npm run dev     # http://localhost:3000
npm run lint
npm run build
```

백엔드가 `localhost:8000`에서 떠 있어야 한다. 반복 작업 중에는 백엔드 `.env`의
`LLM_PROVIDER=mock`을 권장(업로드마다 수 분 대기 방지), 최종 확인 때만 `ollama`로 전환.

"""FigureMate API 엔트리포인트.

M1 작업지시서(docs/milestones/M1.md) 참고.
라우트가 늘어나면 app/api/ 아래에 파일을 추가하고 여기서 include_router 한다.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_figures import router as figures_router
from app.api.routes_papers import router as papers_router

app = FastAPI(
    title="FigureMate API",
    description="Figure 중심 논문 학습 플랫폼 — 백엔드 API",
    version="0.1.0",
)

# M5 프론트엔드(Next.js, localhost:3000)가 브라우저에서 API를 호출할 수 있도록 CORS 허용.
# 로컬 개발용 오리진만 명시한다 (배포 시 실제 도메인으로 교체).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers_router, prefix="/papers", tags=["papers"])
app.include_router(figures_router, prefix="/papers", tags=["figures"])


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}

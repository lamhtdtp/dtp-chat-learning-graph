from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, cms, lessons, tutor, video
from app.config import settings

# Nền tảng giáo trình có cấu trúc (đã bỏ hẳn chat/RAG/sinh-đề — xem P5). Video AI
# giữ lại như tính năng đính kèm. Không còn chat-graph nên không cần lifespan
# dựng graph + Redis checkpointer.
app = FastAPI(title="Gia sư DTP — Giáo trình")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(video.router)
app.include_router(admin.router)
app.include_router(lessons.router)
app.include_router(cms.router)
app.include_router(tutor.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

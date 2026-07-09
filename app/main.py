from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, books, chat, exam, sessions, video
from app.config import settings
from app.graph.build import build_graph_with_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dựng graph + Redis checkpointer 1 lần lúc startup, giữ mở suốt vòng đời
    # app (không dựng lại mỗi request). AsyncExitStack để đóng checkpointer gọn.
    async with AsyncExitStack() as stack:
        app.state.graph = await stack.enter_async_context(build_graph_with_redis())
        yield


app = FastAPI(title="Chat Learning Toán", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(books.router)
app.include_router(exam.router)
app.include_router(video.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

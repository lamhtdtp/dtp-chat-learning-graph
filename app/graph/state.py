"""State cho graph phục vụ chat. Toàn bộ state đi qua checkpointer Redis (app
stateless) — không giữ trong RAM process (xem skill rag-orchestration Phần 2).
"""

from typing import Literal, TypedDict

from app.retrieval.retriever import RetrievedChunk

Intent = Literal["hoi_dap", "giai_bai", "sinh_de", "on_tap"]


class ChatState(TypedDict, total=False):
    messages: list[dict]  # format Anthropic: [{"role", "content"}]
    role: Literal["hoc_sinh", "giao_vien"]
    mon: str  # môn để lọc Qdrant (vd "toan", "tieng_anh"); mặc định toan
    intent: Intent | None
    retrieved: list[RetrievedChunk]
    answer: str | None

"""POST /chat — chạy graph hội thoại, bắt buộc Bearer JWT.

thread_id của checkpointer = "{user_id}:{session_id}" để mỗi phiên chat của mỗi
user tách biệt; state hội thoại sống trong Redis (stateless app). Graph được
dựng 1 lần lúc startup (lifespan) và tái dùng — không dựng lại mỗi request.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db.models import User
from app.llm.gateway import LLMUnavailable

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class Citation(BaseModel):
    nguon: str
    page_no: int
    chuong_so: int | None
    bai_so: int | None


class ChatResponse(BaseModel):
    reply: str
    intent: str | None
    citations: list[Citation]
    session_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> ChatResponse:
    graph = request.app.state.graph
    thread_id = f"{user.id}:{body.session_id}"

    try:
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": body.message}], "role": user.role},
            config={"configurable": {"thread_id": thread_id}},
        )
    except LLMUnavailable:
        # Provider hết quota (429)/mất kết nối -> 503 + thông báo thân thiện,
        # KHÔNG để 500 trần (VNGCloud giới hạn 50 req/ngày rất hay chạm).
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Hệ thống đang bận (quá giới hạn gọi AI), bạn thử lại sau ít phút nhé.",
        )

    retrieved = result.get("retrieved") or []
    citations = [
        Citation(nguon=r.nguon, page_no=r.page_no, chuong_so=r.chuong_so, bai_so=r.bai_so)
        for r in retrieved
    ]
    return ChatResponse(
        reply=result.get("answer") or "",
        intent=result.get("intent"),
        citations=citations,
        session_id=body.session_id,
    )

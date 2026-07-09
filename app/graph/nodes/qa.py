"""Node hỏi-đáp RAG. Hàm thuần (state) -> partial_state, test được bằng mock
gateway + retrieved dựng sẵn trong state (xem tests/graph/test_nodes.py).
"""

from app.graph.grounding import KHONG_TIM_THAY, has_grounding
from app.graph.state import ChatState
from app.llm import gateway
from app.retrieval.retriever import RetrievedChunk

_SYSTEM = (
    "Bạn là trợ lý học Toán lớp 6, trả lời bằng tiếng Việt, thân thiện với học "
    "sinh. CHỈ trả lời dựa trên NGỮ CẢNH SGK được cung cấp; không bịa kiến thức "
    "ngoài ngữ cảnh. Nếu ngữ cảnh không đủ, nói rõ là chưa có trong SGK."
)


def _context_block(retrieved: list[RetrievedChunk]) -> str:
    return "\n\n".join(f"[{r.nguon}]\n{r.content}" for r in retrieved)


async def qa_node(state: ChatState) -> dict:
    retrieved = state.get("retrieved", [])
    if not has_grounding(retrieved):
        return {"answer": f"{KHONG_TIM_THAY}. Em thử hỏi lại theo cách khác nhé!"}

    question = state["messages"][-1]["content"]
    messages = [
        {
            "role": "user",
            "content": (
                f"{_SYSTEM}\n\nNGỮ CẢNH SGK:\n{_context_block(retrieved)}\n\n"
                f"CÂU HỎI: {question}"
            ),
        }
    ]
    # cache_ctx bật semantic cache: chương lấy từ chunk liên quan nhất (điểm cao
    # nhất, đứng đầu retrieved) để câu cùng chương/khối/vai trò dùng chung cache.
    cache_ctx = {
        "question": question,
        "mon": "toan",
        "khoi": "lop_6",
        "chuong": retrieved[0].chuong_so,
        "role": state.get("role", "hoc_sinh"),
    }
    answer = await gateway.complete(task="qa", messages=messages, cache_ctx=cache_ctx)
    return {"answer": answer}

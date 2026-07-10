"""Node giải bài từng bước. Hàm thuần (state) -> partial_state.

Khác qa_node: yêu cầu LLM trình bày TỪNG BƯỚC (không chỉ đáp số), và dùng task
"solve" (tầng mạnh — cần lý luận nhiều bước). Vẫn bám ngữ cảnh SGK, không bịa.
"""

from app.graph.format import MATH_FORMAT as _MATH_FORMAT
from app.graph.grounding import KHONG_TIM_THAY, has_grounding
from app.graph.state import ChatState
from app.llm import gateway
from app.retrieval.retriever import RetrievedChunk

_SYSTEM = (
    "Bạn là trợ lý học Toán lớp 6, trả lời bằng tiếng Việt. Hãy giải bài TỪNG "
    "BƯỚC rõ ràng, không chỉ đưa đáp số, dựa trên phương pháp/ví dụ trong NGỮ "
    "CẢNH SGK được cung cấp. Không bịa phương pháp ngoài ngữ cảnh.\n"
    "Mỗi đoạn ngữ cảnh có nhãn [tr.N] (N là số trang). Khi dùng phương pháp/ví "
    "dụ từ đoạn nào, CHÈN [tr.N] tương ứng vào cuối bước đó. Chỉ dùng số trang "
    "có trong ngữ cảnh.\n"
    + _MATH_FORMAT
)


def _context_block(retrieved: list[RetrievedChunk]) -> str:
    return "\n\n".join(f"[tr.{r.page_no}] {r.content}" for r in retrieved)


async def solve_node(state: ChatState) -> dict:
    retrieved = state.get("retrieved", [])
    if not has_grounding(retrieved):
        return {"answer": f"{KHONG_TIM_THAY}. Em kiểm tra lại đề bài giúp mình nhé!"}

    de_bai = state["messages"][-1]["content"]
    messages = [
        {
            "role": "user",
            "content": (
                f"{_SYSTEM}\n\nNGỮ CẢNH SGK:\n{_context_block(retrieved)}\n\n"
                f"ĐỀ BÀI: {de_bai}"
            ),
        }
    ]
    answer = await gateway.complete(task="solve", messages=messages)
    return {"answer": answer}

"""Node ôn tập: hệ thống lại kiến thức trọng tâm của chủ đề học sinh muốn ôn,
kèm gợi ý vài câu tự luyện — tất cả bám NGỮ CẢNH SGK, không bịa.

Khác qa_node (hỏi-đáp một khái niệm): on_tap tổng hợp lại nhiều ý trong chủ đề
thành dàn bài ôn tập + gợi ý luyện tập (xem full-system-spec mục 7 "on_tap" —
bản tối giản, chưa cần learner_state cá nhân hoá).
"""

from app.graph.format import MATH_FORMAT as _MATH_FORMAT
from app.graph.grounding import KHONG_TIM_THAY, has_grounding
from app.graph.state import ChatState
from app.llm import gateway
from app.retrieval.retriever import RetrievedChunk

_SYSTEM = (
    "Bạn là trợ lý học Toán lớp 6, giúp học sinh ÔN TẬP. Dựa trên NGỮ CẢNH SGK "
    "được cung cấp, hãy: (1) tóm tắt các ý kiến thức trọng tâm cần nhớ dưới dạng "
    "gạch đầu dòng ngắn gọn; (2) gợi ý 2-3 câu tự luyện (kèm đáp án) bám đúng nội "
    "dung đó. CHỈ dùng nội dung trong ngữ cảnh, không bịa kiến thức ngoài ngữ "
    "cảnh; nếu ngữ cảnh không đủ, nói rõ là chưa có trong SGK.\n"
    "Mỗi đoạn ngữ cảnh có nhãn [tr.N] (N là số trang). Khi nêu một ý lấy từ đoạn "
    "nào, CHÈN ngay [tr.N] tương ứng vào cuối ý đó. Chỉ dùng số trang có trong "
    "ngữ cảnh, không bịa số trang.\n"
    + _MATH_FORMAT
)


def _context_block(retrieved: list[RetrievedChunk]) -> str:
    return "\n\n".join(f"[tr.{r.page_no}] {r.content}" for r in retrieved)


async def on_tap_node(state: ChatState) -> dict:
    retrieved = state.get("retrieved", [])
    if not has_grounding(retrieved):
        return {"answer": f"{KHONG_TIM_THAY}. Em thử nêu rõ chủ đề muốn ôn nhé!"}

    chu_de = state["messages"][-1]["content"]
    messages = [
        {
            "role": "user",
            "content": (
                f"{_SYSTEM}\n\nNGỮ CẢNH SGK:\n{_context_block(retrieved)}\n\n"
                f"CHỦ ĐỀ CẦN ÔN: {chu_de}"
            ),
        }
    ]
    answer = await gateway.complete(task="qa", messages=messages)
    return {"answer": answer}

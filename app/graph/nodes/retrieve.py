"""Node truy hồi ngữ cảnh SGK cho câu hỏi hiện tại, đặt vào state["retrieved"].
Tách khỏi qa/solve để hai node đó test được bằng retrieved dựng sẵn (không phải
mock retriever bên trong node).
"""

from app.graph.state import ChatState
from app.retrieval import retriever

# Ngưỡng điểm tối thiểu để coi là "có ngữ cảnh" — dưới ngưỡng bị loại ở retriever,
# rỗng thì guard chống bịa ở qa/solve node sẽ short-circuit.
# 0.40 hiệu chỉnh cho embedding openai/text-embedding-3-large (đo thật trên SGK
# Toán 6): câu ĐÚNG đề khớp ~0.43–0.74, câu LẠC đề ~0.28–0.34 -> 0.40 tách sạch
# (0.5 trước đó là của gemini-embedding, quá cao -> lọc nhầm khớp thật thành
# "không tìm thấy"). Đổi model embedding thì phải đo lại ngưỡng.
_SCORE_THRESHOLD = 0.4
_TOP_K = 5


async def retrieve_node(state: ChatState) -> dict:
    query = state["messages"][-1]["content"]
    # Giải bài: ưu tiên ví dụ/phương pháp hơn lý thuyết suông. Hỏi đáp: không
    # ép loại nội dung. (Chưa lọc theo chương vì chưa suy chương từ câu hỏi —
    # thêm khi có nhu cầu; hiện chỉ 1 sách nên filter mon/khoi là đủ.)
    chunks = await retriever.retrieve(
        query,
        mon="toan",
        khoi="lop_6",
        top_k=_TOP_K,
        score_threshold=_SCORE_THRESHOLD,
    )
    return {"retrieved": chunks}

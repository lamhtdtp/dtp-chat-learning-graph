"""Node truy hồi ngữ cảnh SGK cho câu hỏi hiện tại, đặt vào state["retrieved"].
Tách khỏi qa/solve để hai node đó test được bằng retrieved dựng sẵn (không phải
mock retriever bên trong node).
"""

from app.graph.state import ChatState
from app.retrieval import retriever

# Ngưỡng điểm tối thiểu để coi là "có ngữ cảnh" — dưới ngưỡng bị loại ở retriever,
# rỗng thì guard chống bịa ở qa/solve node sẽ short-circuit. Đặt bảo thủ; chỉnh
# theo eval retrieval sau (chưa có baseline nên để giá trị an toàn).
_SCORE_THRESHOLD = 0.5
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

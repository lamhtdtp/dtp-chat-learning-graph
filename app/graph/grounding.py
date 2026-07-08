"""Guard chống bịa (nguyên tắc vàng #6). Guard nằm TRONG CODE, không phụ thuộc
prompt: nếu không có ngữ cảnh retrieve được thì node trả lời "không tìm thấy
trong SGK" và KHÔNG gọi LLM — vừa tránh bịa vừa tiết kiệm chi phí (xem skill
rag-orchestration Phần C).
"""

from app.retrieval.retriever import RetrievedChunk

KHONG_TIM_THAY = "Mình không tìm thấy nội dung này trong SGK"


def has_grounding(retrieved: list[RetrievedChunk]) -> bool:
    """Có ngữ cảnh để trả lời không. Ngưỡng điểm đã áp ở retriever
    (score_threshold) — tới node chỉ cần kiểm còn chunk nào không."""
    return len(retrieved) > 0

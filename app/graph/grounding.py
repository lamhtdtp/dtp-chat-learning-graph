"""Guard chống bịa (nguyên tắc vàng #6). Guard nằm TRONG CODE, không phụ thuộc
prompt: nếu không có ngữ cảnh retrieve được thì node trả lời "không tìm thấy
trong SGK" và KHÔNG gọi LLM — vừa tránh bịa vừa tiết kiệm chi phí (xem skill
rag-orchestration Phần C).
"""

from app.retrieval.retriever import RetrievedChunk

KHONG_TIM_THAY = "Mình không tìm thấy nội dung này trong SGK"


def has_grounding(retrieved: list[RetrievedChunk], bai_hoc: str | None = None) -> bool:
    """Có ngữ cảnh để trả lời không. Ngưỡng điểm đã áp ở retriever
    (score_threshold) — tới node chỉ cần kiểm còn chunk nào không.

    NỘI DUNG BÀI ĐANG HỌC cũng là căn cứ hợp lệ: học sinh hỏi về đúng đoạn đang
    hiện trên màn hình thì trả "không tìm thấy trong SGK" là sai và rất khó hiểu
    với các em — chữ đang nằm ngay đó. Chỉ khi KHÔNG có cả hai mới từ chối."""
    return len(retrieved) > 0 or bool((bai_hoc or "").strip())

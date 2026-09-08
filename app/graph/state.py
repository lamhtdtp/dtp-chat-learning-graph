"""State cho graph phục vụ chat. Toàn bộ state đi qua checkpointer Redis (app
stateless) — không giữ trong RAM process (xem skill rag-orchestration Phần 2).
"""

from typing import Literal, TypedDict

from app.retrieval.retriever import RetrievedChunk

Intent = Literal["hoi_dap", "giai_bai", "sinh_de", "on_tap"]
PhamVi = Literal["bai", "ca_cuon"]


class ChatState(TypedDict, total=False):
    messages: list[dict]  # format Anthropic: [{"role", "content"}]
    role: Literal["hoc_sinh", "giao_vien"]
    mon: str  # môn để lọc Qdrant (vd "toan", "tieng_anh"); mặc định toan
    intent: Intent | None
    retrieved: list[RetrievedChunk]
    answer: str | None
    # Nội dung ĐƠN VỊ KIẾN THỨC học sinh đang mở, đã cắt theo đoạn đang hỏi.
    # Nguồn ưu tiên hơn SGK: đây đúng là chữ đang hiện trên màn hình của em nó,
    # còn SGK chỉ để đối chiếu. Rỗng = hỏi ngoài trang bài học (vẫn chạy như cũ).
    bai_hoc: str | None
    # Chỉ để tách semantic cache — hai đoạn khác nhau của hai bài khác nhau KHÔNG
    # được dùng chung câu trả lời đã cache.
    topic_id: int | None
    anchor: str | None
    # Khối (dạng Qdrant, vd "lop_6") để tách cache theo khối. Endpoint suy từ
    # `CurriculumTopic.grade_id`; thiếu thì node mặc định lop_6 như cũ.
    khoi: str | None
    # "bai" (mặc định) = hỏi trong đơn vị đang mở, có nội dung bài làm nguồn ưu
    # tiên. "ca_cuon" = hỏi xuyên cả cuốn: bỏ nội dung bài, thêm mục lục, và
    # prompt KHÔNG dặn ưu tiên bài nào.
    pham_vi: PhamVi | None
    # Mục lục cuốn sách (mạch + tên đơn vị) — chỉ dùng ở phạm vi "ca_cuon". Là
    # BẢN ĐỒ, không phải ngữ liệu: không tính là căn cứ grounding.
    muc_luc: str | None

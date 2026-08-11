"""Node hỏi-đáp RAG. Hàm thuần (state) -> partial_state, test được bằng mock
gateway + retrieved dựng sẵn trong state (xem tests/graph/test_nodes.py).
"""

from app.graph.format import MATH_FORMAT as _MATH_FORMAT
from app.graph.grounding import KHONG_TIM_THAY, has_grounding
from app.graph.state import ChatState
from app.llm import gateway
from app.retrieval.retriever import RetrievedChunk

# Tên môn hiển thị trong prompt (state["mon"] là giá trị Qdrant).
_MON_TEN = {"toan": "Toán", "tieng_anh": "Tiếng Anh", "anh": "Tiếng Anh"}

# Nhân vật + cách giải thích theo VAI TRÒ người hỏi. Học sinh: dẫn dắt, khích lệ.
# Giáo viên: súc tích, chuẩn chuyên môn, thêm góc sư phạm để dùng trên lớp.
_PERSONA = {
    "hoc_sinh": (
        "Bạn là trợ lý học {ten} lớp 6, trả lời bằng tiếng Việt, thân thiện với "
        "học sinh. Giải thích từng bước, ngắn gọn, dễ hiểu và khích lệ."
    ),
    "giao_vien": (
        "Bạn đang hỗ trợ một GIÁO VIÊN {ten} lớp 6 (xưng hô 'thầy/cô', không dùng "
        "'em'). Trả lời bằng tiếng Việt, súc tích và chuẩn xác về chuyên môn. "
        "Ngoài phần kiến thức, KHI PHÙ HỢP hãy bổ sung góc nhìn sư phạm ngắn gọn: "
        "(1) cách diễn đạt để học sinh dễ hiểu, (2) lỗi/nhầm lẫn học sinh hay mắc, "
        "(3) 1–2 câu hỏi hoặc ví dụ mở rộng để khai thác trên lớp. Trình bày phần "
        "sư phạm tách riêng, không trộn vào phần kiến thức."
    ),
}

# Quy tắc chung mọi vai trò: chỉ bám ngữ cảnh, trích [tr.N], gạch chân bằng <u>,
# định dạng công thức.
_COMMON = (
    "CHỈ trả lời dựa trên NGỮ CẢNH được cung cấp; không bịa kiến thức ngoài "
    "ngữ cảnh. Nếu ngữ cảnh không đủ, nói rõ là chưa có trong SGK.\n"
    "Khi có khối NGỮ CẢNH BÀI ĐANG HỌC: ƯU TIÊN nó, vì đó đúng là nội dung học "
    "sinh đang mở trên màn hình. Bám sát cách diễn đạt, ký hiệu và các bước giải "
    "trong đó; dẫn lại đúng ví dụ/khái niệm em ấy đang đọc thay vì trình bày một "
    "cách làm khác. NGỮ CẢNH SGK chỉ dùng để bổ sung hoặc đối chiếu.\n"
    "Mỗi đoạn NGỮ CẢNH SGK có nhãn [tr.N] (N là số trang). Khi trình bày một ý "
    "lấy từ đoạn SGK nào, CHÈN ngay [tr.N] tương ứng vào cuối câu/ý đó (ví dụ: "
    "'...số nguyên tố chỉ có hai ước [tr.45].'). Chỉ dùng số trang có trong "
    "ngữ cảnh, không bịa số trang.\n"
    "Ý lấy từ NGỮ CẢNH BÀI ĐANG HỌC thì KHÔNG chèn nhãn nào cả — không viết "
    "'[Bài đang học]', không gán số trang cho nó. Giao diện đã hiện nguồn ở chỗ "
    "khác; nhãn tự chế chỉ làm câu trả lời rối mắt học sinh.\n"
    "Khi cần GẠCH CHÂN một phần chữ (ví dụ âm/chữ cái được gạch chân trong bài "
    "phát âm tiếng Anh), bọc phần đó trong <u>...</u>. TUYỆT ĐỐI KHÔNG dùng dấu "
    "sao * cho gạch chân (dấu sao là in đậm, không phải gạch chân). "
    "Ví dụ đúng: '<u>s</u>ister | hi<u>s</u> | <u>p</u>olice'.\n"
    + _MATH_FORMAT
)


def _system(mon: str, role: str) -> str:
    ten = _MON_TEN.get(mon, "Toán")
    persona = _PERSONA.get(role, _PERSONA["hoc_sinh"]).format(ten=ten)
    return f"{persona}\n{_COMMON}"


def _context_block(retrieved: list[RetrievedChunk]) -> str:
    return "\n\n".join(f"[tr.{r.page_no}] {r.content}" for r in retrieved)


async def qa_node(state: ChatState) -> dict:
    retrieved = state.get("retrieved", [])
    bai_hoc = (state.get("bai_hoc") or "").strip()
    if not has_grounding(retrieved, bai_hoc):
        return {"answer": f"{KHONG_TIM_THAY}. Em thử hỏi lại theo cách khác nhé!"}

    question = state["messages"][-1]["content"]
    mon = state.get("mon", "toan")
    role = state.get("role", "hoc_sinh")
    # Bài đang học đứng TRƯỚC SGK — thứ tự trong prompt cũng là thứ tự ưu tiên.
    khoi_ngu_canh = ""
    if bai_hoc:
        khoi_ngu_canh += f"\n\nNGỮ CẢNH BÀI ĐANG HỌC:\n{bai_hoc}"
    if retrieved:
        khoi_ngu_canh += f"\n\nNGỮ CẢNH SGK:\n{_context_block(retrieved)}"
    messages = [
        {"role": "user", "content": f"{_system(mon, role)}{khoi_ngu_canh}\n\nCÂU HỎI: {question}"}
    ]
    # cache_ctx bật semantic cache: tách theo môn + vai trò (giáo viên/học sinh có
    # giọng khác nhau -> KHÔNG dùng chung câu trả lời); chương lấy từ chunk liên
    # quan nhất (đứng đầu retrieved) cho câu cùng chương/khối dùng chung cache.
    #
    # topic_id + anchor BẮT BUỘC có mặt: cùng một câu hỏi ngắn ("giải thích lại
    # đi") hỏi ở hai đơn vị kiến thức khác nhau là hai câu trả lời khác nhau —
    # thiếu hai khoá này thì cache trả nhầm bài, sai âm thầm và rất khó truy.
    cache_ctx = {
        "question": question,
        "mon": mon,
        "khoi": "lop_6",
        # retrieved có thể RỖNG khi chỉ dựa vào nội dung bài -> không index [0].
        "chuong": retrieved[0].chuong_so if retrieved else None,
        "role": role,
        "topic_id": state.get("topic_id"),
        "anchor": state.get("anchor"),
    }
    answer = await gateway.complete(task="qa", messages=messages, cache_ctx=cache_ctx)
    return {"answer": answer}

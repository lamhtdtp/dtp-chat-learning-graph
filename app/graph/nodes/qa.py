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

# Quy tắc chung mọi vai trò: chỉ bám SGK, trích [tr.N], gạch chân bằng <u>, định
# dạng công thức.
_COMMON = (
    "CHỈ trả lời dựa trên NGỮ CẢNH SGK được cung cấp; không bịa kiến thức ngoài "
    "ngữ cảnh. Nếu ngữ cảnh không đủ, nói rõ là chưa có trong SGK.\n"
    "Mỗi đoạn ngữ cảnh có nhãn [tr.N] (N là số trang). Khi trình bày một ý lấy "
    "từ đoạn nào, CHÈN ngay [tr.N] tương ứng vào cuối câu/ý đó (ví dụ: "
    "'...số nguyên tố chỉ có hai ước [tr.45].'). Chỉ dùng số trang có trong "
    "ngữ cảnh, không bịa số trang.\n"
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
    if not has_grounding(retrieved):
        return {"answer": f"{KHONG_TIM_THAY}. Em thử hỏi lại theo cách khác nhé!"}

    question = state["messages"][-1]["content"]
    mon = state.get("mon", "toan")
    role = state.get("role", "hoc_sinh")
    messages = [
        {
            "role": "user",
            "content": (
                f"{_system(mon, role)}\n\nNGỮ CẢNH SGK:\n{_context_block(retrieved)}\n\n"
                f"CÂU HỎI: {question}"
            ),
        }
    ]
    # cache_ctx bật semantic cache: tách theo môn + vai trò (giáo viên/học sinh có
    # giọng khác nhau -> KHÔNG dùng chung câu trả lời); chương lấy từ chunk liên
    # quan nhất (đứng đầu retrieved) cho câu cùng chương/khối dùng chung cache.
    cache_ctx = {
        "question": question,
        "mon": mon,
        "khoi": "lop_6",
        "chuong": retrieved[0].chuong_so,
        "role": role,
    }
    answer = await gateway.complete(task="qa", messages=messages, cache_ctx=cache_ctx)
    return {"answer": answer}

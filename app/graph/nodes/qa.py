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

# Luật trích số trang — dùng chung cả hai phạm vi.
_LUAT_TRANG = (
    "Mỗi đoạn NGỮ CẢNH SGK có nhãn [tr.N] (N là số trang). Khi trình bày một ý "
    "lấy từ đoạn SGK nào, CHÈN ngay [tr.N] tương ứng vào cuối câu/ý đó (ví dụ: "
    "'...số nguyên tố chỉ có hai ước [tr.45].'). Chỉ dùng số trang có trong "
    "ngữ cảnh, không bịa số trang.\n"
)

# Luật riêng phạm vi CẢ CUỐN. Cố ý KHÔNG có chữ "ƯU TIÊN" nào: câu hỏi ở đây
# thường nhắm chương học sinh chưa tới, dặn ưu tiên một bài là kéo câu trả lời
# lệch về chỗ em ấy đang đứng.
_LUAT_CUON = (
    "Học sinh đang hỏi về TOÀN BỘ cuốn sách, không riêng bài đang mở. Trả lời "
    "dựa trên NGỮ CẢNH SGK, kể cả khi nội dung thuộc chương em ấy chưa học tới.\n"
    "Khối MỤC LỤC là BẢN ĐỒ cuốn sách (tên mạch và tên các đơn vị kiến thức), "
    "KHÔNG phải nội dung. Dùng nó để nói phần nào nằm ở đâu, thứ tự học ra sao, "
    "hoặc gợi ý nên xem bài nào. TUYỆT ĐỐI KHÔNG suy nội dung kiến thức từ một "
    "cái tên trong mục lục — không có đoạn SGK tương ứng thì nói rõ là chưa có "
    "ngữ liệu cho phần đó.\n"
    "Nếu câu hỏi trải nhiều phần của sách, trả lời theo thứ tự các phần xuất "
    "hiện trong mục lục để em ấy dễ lần theo.\n"
    + _LUAT_TRANG
)

# Luật riêng phạm vi TRONG BÀI.
_LUAT_BAI = (
    "Khi có khối NGỮ CẢNH BÀI ĐANG HỌC: ƯU TIÊN nó, vì đó đúng là nội dung học "
    "sinh đang mở trên màn hình. Bám sát cách diễn đạt, ký hiệu và các bước giải "
    "trong đó; dẫn lại đúng ví dụ/khái niệm em ấy đang đọc thay vì trình bày một "
    "cách làm khác. NGỮ CẢNH SGK chỉ dùng để bổ sung hoặc đối chiếu.\n"
    + _LUAT_TRANG +
    "Ý lấy từ NGỮ CẢNH BÀI ĐANG HỌC thì KHÔNG chèn nhãn nào cả — không viết "
    "'[Bài đang học]', không gán số trang cho nó. Giao diện đã hiện nguồn ở chỗ "
    "khác; nhãn tự chế chỉ làm câu trả lời rối mắt học sinh.\n"
)

# Quy tắc chung mọi vai trò: chỉ bám ngữ cảnh, gạch chân bằng <u>, định dạng
# công thức. `{luat_pham_vi}` được thay bằng _LUAT_BAI hoặc _LUAT_CUON.
_COMMON = (
    "CHỈ trả lời dựa trên NGỮ CẢNH được cung cấp; không bịa kiến thức ngoài "
    "ngữ cảnh. Nếu ngữ cảnh không đủ, nói rõ là chưa có trong SGK.\n"
    "{luat_pham_vi}"
    "Khi cần GẠCH CHÂN một phần chữ (ví dụ âm/chữ cái được gạch chân trong bài "
    "phát âm tiếng Anh), bọc phần đó trong <u>...</u>. TUYỆT ĐỐI KHÔNG dùng dấu "
    "sao * cho gạch chân (dấu sao là in đậm, không phải gạch chân). "
    "Ví dụ đúng: '<u>s</u>ister | hi<u>s</u> | <u>p</u>olice'.\n"
    + _MATH_FORMAT
)


def _system(mon: str, role: str, pham_vi: str) -> str:
    ten = _MON_TEN.get(mon, "Toán")
    persona = _PERSONA.get(role, _PERSONA["hoc_sinh"]).format(ten=ten)
    # replace, KHÔNG format: _MATH_FORMAT chứa LaTeX có dấu ngoặc nhọn
    # (\frac{a}{b}) nên .format() sẽ ném KeyError.
    luat = _LUAT_CUON if pham_vi == "ca_cuon" else _LUAT_BAI
    return f"{persona}\n{_COMMON.replace('{luat_pham_vi}', luat)}"


def _context_block(retrieved: list[RetrievedChunk]) -> str:
    return "\n\n".join(f"[tr.{r.page_no}] {r.content}" for r in retrieved)


async def qa_node(state: ChatState) -> dict:
    pham_vi = state.get("pham_vi") or "bai"
    ca_cuon = pham_vi == "ca_cuon"
    retrieved = state.get("retrieved", [])
    # Cả cuốn thì BỎ nội dung bài kể cả khi chỗ gọi lỡ truyền vào: để lại là mô
    # hình có một bài cụ thể trong tay và câu trả lời lại bám về đó.
    bai_hoc = "" if ca_cuon else (state.get("bai_hoc") or "").strip()
    # Mục lục KHÔNG tính là grounding: nó chỉ có tên các bài, trả lời nội dung
    # dựa vào tên là đúng nghĩa bịa.
    if not has_grounding(retrieved, bai_hoc):
        return {"answer": f"{KHONG_TIM_THAY}. Em thử hỏi lại theo cách khác nhé!"}

    question = state["messages"][-1]["content"]
    mon = state.get("mon", "toan")
    role = state.get("role", "hoc_sinh")
    # Bài đang học đứng TRƯỚC SGK — thứ tự trong prompt cũng là thứ tự ưu tiên.
    khoi_ngu_canh = ""
    if bai_hoc:
        khoi_ngu_canh += f"\n\nNGỮ CẢNH BÀI ĐANG HỌC:\n{bai_hoc}"
    if ca_cuon and (muc_luc := (state.get("muc_luc") or "").strip()):
        khoi_ngu_canh += f"\n\nMỤC LỤC CUỐN SÁCH:\n{muc_luc}"
    if retrieved:
        khoi_ngu_canh += f"\n\nNGỮ CẢNH SGK:\n{_context_block(retrieved)}"
    messages = [
        {"role": "user",
         "content": f"{_system(mon, role, pham_vi)}{khoi_ngu_canh}\n\nCÂU HỎI: {question}"}
    ]
    # cache_ctx bật semantic cache: tách theo môn + vai trò (giáo viên/học sinh có
    # giọng khác nhau -> KHÔNG dùng chung câu trả lời); chương lấy từ chunk liên
    # quan nhất (đứng đầu retrieved) cho câu cùng chương/khối dùng chung cache.
    #
    # topic_id + anchor + pham_vi BẮT BUỘC có mặt: cùng một câu hỏi ngắn ("giải
    # thích lại đi") hỏi ở hai đơn vị kiến thức — hoặc ở hai phạm vi — là hai câu
    # trả lời khác nhau; thiếu khoá nào thì cache trả nhầm, sai âm thầm và rất
    # khó truy. (Gateway trước đây bỏ rơi chúng, xem app/llm/gateway.py.)
    cache_ctx = {
        "question": question,
        "mon": mon,
        # Khối lấy từ state — hardcode "lop_6" ở đây khiến câu trả lời lẫn giữa
        # các khối ngay khi nạp cuốn thứ hai. Mặc định giữ lop_6 cho chỗ gọi cũ.
        "khoi": state.get("khoi") or "lop_6",
        # retrieved có thể RỖNG khi chỉ dựa vào nội dung bài -> không index [0].
        "chuong": retrieved[0].chuong_so if retrieved else None,
        "role": role,
        "topic_id": state.get("topic_id"),
        "anchor": state.get("anchor"),
        "pham_vi": pham_vi,
    }
    answer = await gateway.complete(task="qa", messages=messages, cache_ctx=cache_ctx)
    return {"answer": answer}

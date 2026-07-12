"""Node sinh đề: soạn câu hỏi cho phần CÒN THIẾU so với chỉ tiêu.

LLM chỉ soạn NỘI DUNG câu hỏi (task=exam_gen, tầng mạnh) — việc đếm/phân bổ do
code (build_blueprint/check). Nội dung bám ngữ liệu SGK retrieve được, không bịa
(nguyên tắc vàng #6). Mỗi lần lặp CHỈ sinh bù phần thiếu, không sinh lại từ đầu
(xem skill exam-generation).
"""

import json

from app.exam.check import CauHoi, DeThi, tinh_phan_thieu
from app.graph.exam_state import ExamState
from app.llm import gateway
from app.retrieval import retriever

# Tên môn hiển thị trong prompt (state["mon"] là giá trị Qdrant). Thêm môn = 1 dòng.
_MON_TEN = {"toan": "Toán", "tieng_anh": "Tiếng Anh", "anh": "Tiếng Anh"}


def _system(mon: str) -> str:
    ten = _MON_TEN.get(mon, "Toán")
    return (
        f"Bạn là giáo viên {ten} lớp 6 soạn câu hỏi kiểm tra. Soạn câu hỏi bám sát "
        "NGỮ CẢNH SGK được cung cấp, không bịa nội dung ngoài ngữ cảnh. Trả về JSON "
        'thuần dạng: {"cau_hoi": [{"muc_do": "de|trung_binh|kho", "noi_dung": "...", '
        '"dap_an": "...", "loi_giai": "..."}]}. Số câu mỗi mức đúng như yêu cầu.'
    )


def _salvage_objects(text: str) -> list[dict]:
    """Vớt các object {...} HOÀN CHỈNH khi JSON tổng bị cắt (unterminated string
    do LLM chạm max_tokens). Quét theo ngoặc nhọn, tôn trọng chuỗi/escape; chỉ
    giữ object là 1 câu hỏi (có "noi_dung"). Câu cuối bị cắt bị bỏ — check_node
    thấy thiếu và vòng lặp sinh bù tiếp."""
    objs: list[dict] = []
    stack: list[int] = []
    in_str = esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            frag = text[stack.pop():i + 1]
            try:
                obj = json.loads(frag)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "noi_dung" in obj:
                objs.append(obj)
    return objs


def _parse_cau_hoi(raw: str) -> list[CauHoi]:
    """Bóc JSON (kể cả khi LLM bọc trong ```json). JSON bị cắt -> vớt câu hoàn
    chỉnh thay vì sập. Câu sai muc_do bị bỏ qua; check_node sinh bù tiếp."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    try:
        data = json.loads(text)
        items = data.get("cau_hoi", []) if isinstance(data, dict) else []
    except json.JSONDecodeError:
        items = _salvage_objects(text)
    cau_hoi = []
    for item in items:
        try:
            cau_hoi.append(CauHoi.model_validate(item))
        except Exception:
            continue
    return cau_hoi


def _yeu_cau_text(phan_thieu: dict[str, int]) -> str:
    ten = {"de": "dễ", "trung_binh": "trung bình", "kho": "khó"}
    return ", ".join(f"{so} câu mức {ten[md]}" for md, so in phan_thieu.items())


async def exam_gen_node(state: ExamState) -> dict:
    de_hien_tai = DeThi(cau_hoi=list(state.get("de_thi", [])))
    phan_thieu = tinh_phan_thieu(de_hien_tai, state["chi_tieu"])
    if not phan_thieu:
        return {}

    chunks = await retriever.retrieve(
        state["mach_noi_dung"],
        mon=state.get("mon", "toan"), khoi=state.get("khoi", "lop_6"),
        top_k=5, score_threshold=0.4,
    )
    context = "\n\n".join(f"[{c.nguon}]\n{c.content}" for c in chunks)

    messages = [
        {
            "role": "user",
            "content": (
                f"{_system(state.get('mon', 'toan'))}\n\nNGỮ CẢNH SGK:\n{context}\n\n"
                f"MẠCH NỘI DUNG: {state['mach_noi_dung']}\n"
                f"CẦN SOẠN: {_yeu_cau_text(phan_thieu)}."
            ),
        }
    ]
    # Model "strong" tiêu ~2400 token suy nghĩ ẩn tính vào max_tokens; đề nhiều câu
    # (nội dung + lời giải dài) dễ bị cắt ở 4096 -> JSON hỏng. Nâng để đủ chỗ.
    raw = await gateway.complete(task="exam_gen", messages=messages, max_tokens=8192)
    moi = _parse_cau_hoi(raw)

    return {
        "de_thi": list(state.get("de_thi", [])) + moi,
        "so_lan_lap": state.get("so_lan_lap", 0) + 1,
    }

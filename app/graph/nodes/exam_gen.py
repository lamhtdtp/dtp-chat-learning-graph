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

_SYSTEM = (
    "Bạn là giáo viên Toán lớp 6 soạn câu hỏi kiểm tra. Soạn câu hỏi bám sát "
    "NGỮ CẢNH SGK được cung cấp, không bịa nội dung ngoài ngữ cảnh. Trả về JSON "
    'thuần dạng: {"cau_hoi": [{"muc_do": "de|trung_binh|kho", "noi_dung": "...", '
    '"dap_an": "...", "loi_giai": "..."}]}. Số câu mỗi mức đúng như yêu cầu.'
)


def _parse_cau_hoi(raw: str) -> list[CauHoi]:
    """Bóc JSON (kể cả khi LLM bọc trong ```json). Câu sai muc_do bị bỏ qua ở
    đây; check_node sẽ phát hiện thiếu và vòng lặp sinh bù tiếp."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    data = json.loads(text)
    cau_hoi = []
    for item in data.get("cau_hoi", []):
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
                f"{_SYSTEM}\n\nNGỮ CẢNH SGK:\n{context}\n\n"
                f"MẠCH NỘI DUNG: {state['mach_noi_dung']}\n"
                f"CẦN SOẠN: {_yeu_cau_text(phan_thieu)}."
            ),
        }
    ]
    raw = await gateway.complete(task="exam_gen", messages=messages)
    moi = _parse_cau_hoi(raw)

    return {
        "de_thi": list(state.get("de_thi", [])) + moi,
        "so_lan_lap": state.get("so_lan_lap", 0) + 1,
    }

"""Router phân loại ý định học sinh: hoi_dap | giai_bai | on_tap. (sinh_de đi
endpoint riêng /exam/generate, không qua router chat — xem app/api/exam.py.)

Rule-based trước (rẻ, tất định, test được), chỉ gọi LLM khi rule không chắc —
tránh tốn 1 LLM call cho mỗi tin nhắn chỉ để phân loại.
"""

import re

from app.graph.state import ChatState, Intent
from app.llm import gateway

# Đề bài cần giải thường có phép tính/biểu thức: chuỗi số + toán tử, hoặc từ
# khoá mệnh lệnh "tính/giải/tìm x". Có thì gần như chắc là giai_bai.
_EXPR_RE = re.compile(r"\d\s*[-+*/×:².^]\s*\d|=|\btìm\s+x\b", re.IGNORECASE)
_SOLVE_KEYWORDS = ("tính", "giải", "tìm x", "rút gọn", "tính giá trị", "thực hiện phép")
_QA_KEYWORDS = ("là gì", "thế nào", "tại sao", "khái niệm", "định nghĩa", "vì sao")
# Ý định ôn tập: tổng hợp lại kiến thức của cả chủ đề/chương (khác hỏi 1 khái
# niệm hay giải 1 bài). Kiểm tra trước vì "ôn tập" là tín hiệu mạnh, rõ ràng.
_ONTAP_KEYWORDS = ("ôn tập", "ôn lại", "ôn thi", "củng cố", "tổng ôn", "ôn chương",
                   "hệ thống lại", "ôn chủ đề")


def route_rule_based(text: str) -> Intent | None:
    low = text.lower()
    if any(kw in low for kw in _ONTAP_KEYWORDS):
        return "on_tap"
    if any(kw in low for kw in _QA_KEYWORDS):
        return "hoi_dap"
    if _EXPR_RE.search(text) or any(kw in low for kw in _SOLVE_KEYWORDS):
        return "giai_bai"
    return None


async def route_intent(text: str) -> Intent:
    intent = route_rule_based(text)
    if intent is not None:
        return intent

    # Rule không chắc -> hỏi LLM tầng rẻ, ép trả đúng 1 nhãn.
    messages = [
        {
            "role": "user",
            "content": (
                "Phân loại câu sau của học sinh vào ĐÚNG một nhãn, chỉ trả nhãn:\n"
                "- hoi_dap: hỏi khái niệm/lý thuyết\n"
                "- giai_bai: nhờ giải một bài tập cụ thể\n"
                "- on_tap: muốn ôn tập/hệ thống lại kiến thức cả một chủ đề\n\n"
                f"Câu: {text}\nNhãn:"
            ),
        }
    ]
    raw = (await gateway.complete(task="route_intent", messages=messages)).strip().lower()
    if "on_tap" in raw:
        return "on_tap"
    return "giai_bai" if "giai_bai" in raw else "hoi_dap"


async def router_node(state: ChatState) -> dict:
    text = state["messages"][-1]["content"]
    return {"intent": await route_intent(text)}

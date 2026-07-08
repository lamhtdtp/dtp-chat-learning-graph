"""Router phân loại ý định. Phase này chỉ định tuyến học sinh: hoi_dap |
giai_bai (sinh_de/on_tap thêm khi node tương ứng sẵn sàng).

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


def route_rule_based(text: str) -> Intent | None:
    low = text.lower()
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
                "- giai_bai: nhờ giải một bài tập cụ thể\n\n"
                f"Câu: {text}\nNhãn:"
            ),
        }
    ]
    raw = (await gateway.complete(task="route_intent", messages=messages)).strip().lower()
    return "giai_bai" if "giai_bai" in raw else "hoi_dap"


async def router_node(state: ChatState) -> dict:
    text = state["messages"][-1]["content"]
    return {"intent": await route_intent(text)}

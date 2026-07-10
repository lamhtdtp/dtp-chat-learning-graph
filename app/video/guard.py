"""Guard chặn kịch bản video sai TRƯỚC khi tốn công render (US-17 Scenario 4).

Cổng tất định phát hiện công thức LỆCH với câu trả lời đã grounding: nếu kịch
bản đưa một đẳng thức SỐ HỌC có cùng vế trái nhưng vế phải KHÁC đáp án đã có
(vd đáp án '2^3=8' nhưng kịch bản ghi '2^3=9') -> chặn, không render. Cách diễn
đạt lại (đổi ký hiệu, viết tập hợp kiểu khác) KHÔNG bị coi là lệch — tránh chặn
oan. Grounding ngữ nghĩa sâu là lớp [llm-eval] riêng, không thuộc gate này.

Sai công thức số học nguy hại hơn sai chữ (học sinh tin video) -> gate cứng.
"""

import re
from dataclasses import dataclass

from app.video.script import Storyboard


@dataclass
class GuardResult:
    ok: bool
    reason: str | None = None


_LATEX_UNIFY = [
    (r"\left", ""), (r"\right", ""), (r"\,", ""), (r"\!", ""), (r"\;", ""),
    (r"\cdot", "."), (r"\times", "."), (r"\div", "/"),
    (r"\{", "{"), (r"\}", "}"), (r"\mid", "|"), (r"\vert", "|"),
    (r"\neq", "≠"), (r"\ne", "≠"), (r"\leq", "≤"), (r"\le", "≤"),
    (r"\geq", "≥"), (r"\ge", "≥"),
]


def _chuan_hoa(s: str) -> str:
    """Hạ chữ thường, hợp nhất ký hiệu LaTeX/thường, bỏ \\text{...}, '$', khoảng
    trắng, backslash còn sót."""
    out = s.lower()
    out = re.sub(r"\\text\{([^}]*)\}", r"\1", out)  # \text{...} -> nội dung
    for latex, plain in _LATEX_UNIFY:
        out = out.replace(latex, plain)
    out = out.replace("\\", "")
    return re.sub(r"[\s$]+", "", out)


def _is_numeric(side: str) -> bool:
    """Vế 'số học đơn': có chữ số, KHÔNG có chữ cái, và KHÔNG có ký hiệu tập hợp/
    liệt kê ({}|;,) — để chỉ so sánh đẳng thức số vô hướng (2^3=8), bỏ qua tập
    hợp/nhãn ký hiệu (A={0;2;4}) vốn có thể viết nhiều kiểu tương đương."""
    if any(c.isalpha() for c in side) or any(c in side for c in "{}|;,"):
        return False
    return any(c.isdigit() for c in side)


def _equations(text: str) -> list[tuple[str, str]]:
    """Các đẳng thức 'vế trái = vế phải' đã chuẩn hoá (bỏ ==, <=, >=, !=)."""
    eqs = []
    for seg in re.findall(r"\$([^$]+)\$", text) or [text]:
        norm = _chuan_hoa(seg)
        # chỉ '=' đơn (không ≤ ≥ ≠ và không phần của ==)
        if norm.count("=") != 1:
            continue
        lhs, rhs = norm.split("=")
        if lhs and rhs:
            eqs.append((lhs, rhs))
    return eqs


def check_formulas(storyboard: Storyboard, answer: str) -> list[str]:
    """Trả về công thức MÂU THUẪN với câu trả lời (rỗng = đạt): cùng vế trái số
    học nhưng vế phải khác đáp án đã grounding."""
    ans: dict[str, set[str]] = {}
    for lhs, rhs in _equations(answer):
        ans.setdefault(lhs, set()).add(rhs)

    lech: list[str] = []
    for ct in storyboard.tat_ca_cong_thuc():
        for lhs, rhs in _equations(ct):
            known = ans.get(lhs)
            if known and rhs not in known and _is_numeric(rhs) and any(_is_numeric(r) for r in known):
                lech.append(ct)
                break
    return lech


def check_script(storyboard: Storyboard, answer: str) -> GuardResult:
    """Cổng chặn tất định: đạt khi có nội dung và không mâu thuẫn công thức số."""
    if not storyboard.slides:
        return GuardResult(ok=False, reason="Kịch bản rỗng")
    lech = check_formulas(storyboard, answer)
    if lech:
        return GuardResult(ok=False, reason=f"Công thức mâu thuẫn đáp án: {lech}")
    return GuardResult(ok=True)

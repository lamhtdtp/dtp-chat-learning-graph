"""Guard chặn kịch bản video sai/bịa TRƯỚC khi tốn công render (US-17).

Hai lớp:
1. Công thức (tất định, [tdd-core] Scenario 4): mọi công thức xuất hiện trong
   kịch bản PHẢI truy được về câu trả lời đã grounding. Kịch bản bịa công thức
   lệch -> chặn, không render.
2. Grounding văn bản ([llm-eval] Scenario 1/3): dùng LLM-judge đối chiếu kịch
   bản với câu trả lời. Tách riêng, KHÔNG bắt buộc trong luồng tất định.

Sai công thức nguy hại hơn sai chữ (học sinh tin video) -> đây là cổng chặn
phát hành, không phải cảnh báo mềm.
"""

import re
from dataclasses import dataclass

from app.video.script import Storyboard


@dataclass
class GuardResult:
    ok: bool
    reason: str | None = None


def _chuan_hoa(s: str) -> str:
    """Bỏ '$', mọi khoảng trắng, hạ chữ thường — để so khớp công thức bất kể
    cách trình bày ('a . b = b . a' == 'a.b=b.a')."""
    return re.sub(r"[\s$]+", "", s).lower()


def check_formulas(storyboard: Storyboard, answer: str) -> list[str]:
    """Trả về danh sách công thức trong kịch bản KHÔNG truy được về câu trả lời
    (rỗng = đạt). So khớp bằng chứa chuỗi đã chuẩn hoá — công thức của kịch bản
    phải là một phần công thức/nội dung trong câu trả lời gốc."""
    pool = _chuan_hoa(answer)
    lech: list[str] = []
    for ct in storyboard.tat_ca_cong_thuc():
        norm = _chuan_hoa(ct)
        if norm and norm not in pool:
            lech.append(ct)
    return lech


def check_script(storyboard: Storyboard, answer: str) -> GuardResult:
    """Cổng chặn tất định: đạt khi không có công thức lệch và có nội dung."""
    if not storyboard.slides:
        return GuardResult(ok=False, reason="Kịch bản rỗng")
    lech = check_formulas(storyboard, answer)
    if lech:
        return GuardResult(ok=False, reason=f"Công thức không bám câu trả lời: {lech}")
    return GuardResult(ok=True)

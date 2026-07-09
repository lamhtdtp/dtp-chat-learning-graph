"""Sinh kịch bản (storyboard) video từ câu trả lời ĐÃ grounding.

Kịch bản chỉ DIỄN ĐẠT LẠI câu trả lời đã bám SGK thành các slide ngắn + lời
thoại — không thêm khái niệm mới (guard ở app/video/guard.py chặn nếu thêm).
Mọi lời gọi LLM đi qua app/llm gateway (US-17 Scenario 2), không gọi thẳng SDK.
"""

import json

from pydantic import BaseModel, Field

from app.llm import gateway


class Slide(BaseModel):
    tieu_de: str = ""
    y_chinh: list[str] = Field(default_factory=list)   # gạch đầu dòng
    cong_thuc: list[str] = Field(default_factory=list)  # LaTeX (không có $)
    loi_thoai: str = ""                                 # lời thuyết minh TTS


class Storyboard(BaseModel):
    tieu_de: str = ""
    slides: list[Slide] = Field(default_factory=list)

    def loi_thoai_full(self) -> str:
        return " ".join(s.loi_thoai.strip() for s in self.slides if s.loi_thoai.strip())

    def tat_ca_cong_thuc(self) -> list[str]:
        return [ct for s in self.slides for ct in s.cong_thuc]


_SYSTEM = (
    "Bạn là biên kịch video học Toán lớp 6 (30-90 giây). Dựa CHỈ trên CÂU TRẢ "
    "LỜI đã kiểm chứng dưới đây, soạn kịch bản 2-4 slide ngắn gọn, dễ hiểu cho "
    "học sinh. TUYỆT ĐỐI không thêm khái niệm/ví dụ/công thức nằm ngoài câu trả "
    "lời. Công thức để dạng LaTeX KHÔNG kèm dấu $.\n"
    "Trả về JSON thuần dạng: "
    '{"tieu_de": "...", "slides": [{"tieu_de": "...", "y_chinh": ["..."], '
    '"cong_thuc": ["a.b=b.a"], "loi_thoai": "..."}]}'
)


def _parse(raw: str) -> Storyboard:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    return Storyboard.model_validate(json.loads(text))


async def generate_script(answer: str, *, sources: str = "") -> Storyboard:
    content = f"{_SYSTEM}\n\nCÂU TRẢ LỜI ĐÃ KIỂM CHỨNG:\n{answer}"
    if sources:
        content += f"\n\nNGUỒN SGK:\n{sources}"
    raw = await gateway.complete(task="video_script", messages=[{"role": "user", "content": content}])
    return _parse(raw)

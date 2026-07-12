"""Vision OCR từng trang ảnh SGK -> markdown có cấu trúc.

Thay cho "đọc docx/pdf text" — SGK ở đây là ảnh scan nên MỌI trang đều cần
vision (xem specs/full-system-spec.md mục 6). Gọi qua app.llm.gateway (task=
"ocr_page", tầng rẻ flash-lite — OCR không cần reasoning, xem TASK_TIER).

Idempotent theo trang: kết quả markdown mỗi trang lưu vào data_processed/ để
retry KHÔNG phải gọi lại vision LLM cho toàn bộ ~294 trang khi 1 trang lỗi
(vision-extraction có chi phí/độ trễ đáng kể — pilot vài trang trước khi chạy
hết, xem CLI --pages).
"""

import base64
from pathlib import Path

from app.llm import gateway

# OCR prompt theo môn: Toán nhấn công thức LaTeX + giữ ký hiệu; môn khác (vd
# Tiếng Anh) giữ nguyên văn bản gốc + cấu trúc hội thoại/từ vựng/bảng.
_MATH_PROMPT = (
    "Trích xuất TOÀN BỘ nội dung trang sách giáo khoa Toán này thành markdown "
    "tiếng Việt. Yêu cầu:\n"
    "- Công thức toán viết bằng LaTeX (dùng $...$).\n"
    "- Giữ NGUYÊN ký hiệu gốc trong sách, KHÔNG tự diễn giải (ví dụ dấu '.' "
    "giữa hai số cứ giữ là '.', không đổi thành '×').\n"
    "- Nếu trang có tiêu đề Chương hoặc Bài, viết thành heading markdown "
    "(ví dụ '# Bài 1: ...', '# Chương 2: ...').\n"
    "- Với hình minh hoạ không mang nội dung toán, ghi chú ngắn gọn trong "
    "ngoặc, đừng bịa nội dung.\n"
    "Chỉ trả về markdown, không thêm lời giải thích."
)
_GENERAL_PROMPT = (
    "Trích xuất TOÀN BỘ nội dung trang sách giáo khoa này thành markdown. Yêu cầu:\n"
    "- GIỮ NGUYÊN văn bản gốc (giữ tiếng Anh nếu là tiếng Anh, giữ phần tiếng "
    "Việt nếu có); không dịch, không diễn giải, không bịa.\n"
    "- Nếu trang có tiêu đề Unit/Lesson/Chương/Bài, viết thành heading markdown "
    "(ví dụ '# Unit 1: My New School', '## Lesson 1').\n"
    "- Giữ cấu trúc: bảng từ vựng, hội thoại (mỗi lượt 1 dòng), bài đọc, câu hỏi/"
    "bài tập đánh số; nếu có công thức thì dùng LaTeX $...$.\n"
    "- Với hình minh hoạ, ghi chú ngắn gọn trong ngoặc.\n"
    "Chỉ trả về markdown, không thêm lời giải thích."
)

# Giữ tên cũ để tương thích (mặc định Toán).
OCR_PROMPT = _MATH_PROMPT


def _prompt_for(mon: str) -> str:
    return _MATH_PROMPT if mon in ("toan", "maths") else _GENERAL_PROMPT


def _image_b64(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode()


async def ocr_page_image(image_path: Path, mon: str = "toan") -> str:
    """OCR 1 ảnh trang -> markdown. Prompt chọn theo môn. Không cache — caller
    (ingest_book/CLI) lo phần cache idempotent qua `load_or_ocr_page`."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": _prompt_for(mon)},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": _image_b64(image_path),
                    },
                },
            ],
        }
    ]
    return await gateway.complete("ocr_page", messages)


async def load_or_ocr_page(image_path: Path, cache_path: Path, force: bool = False,
                           mon: str = "toan") -> str:
    """Trả markdown của trang; nếu đã có file cache thì đọc lại (idempotent),
    ngược lại OCR rồi ghi cache. `force=True` bỏ qua cache, OCR lại."""
    if cache_path.exists() and not force:
        return cache_path.read_text(encoding="utf-8")

    markdown = await ocr_page_image(image_path, mon=mon)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(markdown, encoding="utf-8")
    return markdown

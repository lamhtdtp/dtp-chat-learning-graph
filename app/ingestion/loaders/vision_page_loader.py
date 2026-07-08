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

OCR_PROMPT = (
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


def _image_b64(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode()


async def ocr_page_image(image_path: Path) -> str:
    """OCR 1 ảnh trang -> markdown. Không cache — caller (ingest_book/CLI) lo
    phần cache idempotent qua `load_or_ocr_page`."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": OCR_PROMPT},
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


async def load_or_ocr_page(image_path: Path, cache_path: Path, force: bool = False) -> str:
    """Trả markdown của trang; nếu đã có file cache thì đọc lại (idempotent),
    ngược lại OCR rồi ghi cache. `force=True` bỏ qua cache, OCR lại."""
    if cache_path.exists() and not force:
        return cache_path.read_text(encoding="utf-8")

    markdown = await ocr_page_image(image_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(markdown, encoding="utf-8")
    return markdown

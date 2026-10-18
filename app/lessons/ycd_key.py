"""Khoá so khớp nguyên văn "yêu cầu cần đạt" — dùng chung cho hai việc:

1. **Gom lịch sử làm bài theo YCCĐ** (`QuizAttemptItem.ycd_key`). Không gom được
   bằng `blueprint_cells.id`: nạp lại ma trận là xoá sạch cell cũ rồi chèn cell
   mới (`app/seed_matrix.py`, `app/seed_curriculum.py` đều `delete(BlueprintCell)`),
   nên khoá ngoại trỏ vào đó sẽ chết đúng kiểu mà `QuizAttempt` từng tránh khi cố
   ý không lưu chỉ số câu.

2. **Khớp YCCĐ của mình với YCCĐ của DTP Testbank.** Testbank tra câu hỏi theo
   nguyên văn YCCĐ đã chuẩn hoá (`ar.yccd_key`, cột Postgres sinh tự động).

Quy tắc dưới đây **chép đúng** từ `services/content/src/content_service/ar_key.py`
của testbank — hai bên phải cho ra cùng một chuỗi, nếu không thì câu hỏi gắn vào
YCCĐ sai mà không có gì báo. Bản SQL phía họ:

    lower(btrim(regexp_replace(normalize(yccd_text, NFC), '\\s+', ' ', 'g')))

KHÔNG bỏ dấu và KHÔNG cắt dấu câu: hai YCCĐ chỉ khác nhau một dấu phẩy là hai
YCCĐ khác nhau. So khớp lỏng tay ở đây là gắn sai mà không ai biết.
"""

import re
import unicodedata

_KHOANG_TRANG = re.compile(r"\s+")


def chuan_hoa(text: str) -> str:
    """NFC → gộp khoảng trắng → bỏ khoảng trắng hai đầu → thường hoá.

    Chịu được khoảng trắng Unicode (NBSP, thin space) và chữ ở dạng tổ hợp dấu
    NFD — hai thứ hay lẫn vào khi nguyên văn được chép từ Word.
    """
    if not text:
        return ""
    return _KHOANG_TRANG.sub(" ", unicodedata.normalize("NFC", text)).strip().lower()

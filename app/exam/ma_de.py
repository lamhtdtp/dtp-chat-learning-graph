"""Mã giao đề (US-26): 6 ký tự giáo viên đọc cho cả lớp.

Bảng ký tự bỏ `0 O 1 I L`: đọc to và chép tay rất dễ nhầm 0/O, 1/I/L — cả lớp gõ
sai thì vào "không tìm thấy mã" dù giáo viên không sai. 31^6 ≈ 887 triệu mã; chống
dò mã ở `app/api/de_giao.py` (10 mã sai / 10 phút).

Sinh bằng `secrets` chứ không phải `random`: Mersenne Twister đoán được đầu ra kế
tiếp từ vài mã đã thấy, và mã không được suy ra từ giờ tạo hay số thứ tự.
Tính duy nhất do unique trong DB + sinh lại khi trùng, không nằm ở đây.
"""
import re
import secrets

BANG_KY_TU = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
DO_DAI = 6
_KHUON = re.compile(f"[{BANG_KY_TU}]{{{DO_DAI}}}")


def sinh_ma() -> str:
    return "".join(secrets.choice(BANG_KY_TU) for _ in range(DO_DAI))


def chuan_hoa_ma(s: str) -> str | None:
    """Bỏ MỌI khoảng trắng, đổi hoa. Sai định dạng -> None (không đoán, không cắt)."""
    ma = "".join((s or "").split())
    # ASCII TRƯỚC khi đổi hoa: `.upper()` biến "ſ" thành "S" và "ß" thành "SS", nên mã gõ
    # bằng ký tự lạ lại khớp một mã thật (và "ß" làm đổi cả độ dài).
    if not ma.isascii():
        return None
    ma = ma.upper()
    return ma if _KHUON.fullmatch(ma) else None

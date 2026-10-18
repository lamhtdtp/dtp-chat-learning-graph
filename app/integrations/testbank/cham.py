"""Chấm một câu rút từ DTP Testbank.

Chạy ở máy chủ learning: `answer_key` không bao giờ xuống trình duyệt trước khi
nộp (docs/24-HUONG-DAN-API-CHO-LEARNING.md §10 của testbank).

Luật chép đúng §7 của tài liệu đó, KHÔNG tự nới. Ví dụ "3.510.000" với
"3510000": người đọc thấy là một số, nhưng testbank không bỏ dấu chấm phân cách
nghìn — mình nới ra là cùng một bài làm, hai hệ thống chấm ra hai điểm, và học
sinh hỏi thầy cô thì không ai giải thích được vì sao.

Hàm thuần, không I/O — để test hết ca biên mà không cần testbank chạy.
"""
import re
from dataclasses import dataclass

from app.integrations.testbank.hien_thi import co_anh

_TACH = re.compile(r"[,;/]")
_KHOANG_TRANG = re.compile(r"\s+")


@dataclass(frozen=True)
class KetQuaCham:
    #: False = câu không chấm tự động được (tự luận, đáp số là ảnh…). Câu đó
    #: KHÔNG tính vào tổng điểm — tính vào là học sinh mất điểm vì giới hạn của
    #: máy chứ không vì làm sai.
    cham_duoc: bool
    dung: bool
    #: Chỉ có ở dạng DS: đúng mấy ý trên mấy ý. Sai một ý vẫn là "sai câu",
    #: nhưng "3/4 ý" nói với học sinh nhiều hơn chữ "sai".
    so_y_dung: int | None = None
    so_y: int | None = None


_KHONG_CHAM = KetQuaCham(cham_duoc=False, dung=False)


def tach_khoa(s: str | None) -> list[str]:
    """"A, c" -> ["A", "C"]. Nhận `,` `;` `/` như máy chủ testbank khi tách."""
    return [p.strip().upper() for p in _TACH.split(s or "") if p.strip()]


def _y_ds(s: str | None) -> list[str]:
    """Tách đáp án Đ/S GIỮ VỊ TRÍ (ý bỏ trống vẫn là một ô) và coi `D` không dấu
    là `Đ` — testbank báo trước là có thể gặp ở dữ liệu nhập tay."""
    return ["Đ" if p in ("D", "Đ") else p for p in
            (x.strip().upper() for x in _TACH.split(s or ""))]


def _chuan_dsn(s: str) -> str:
    """Luật chấm điền đáp số của testbank: bỏ MỌI khoảng trắng, thường hoá, `,` = `.`."""
    return _KHOANG_TRANG.sub("", s).lower().replace(",", ".")


def cham(dang: str, dap_an: str | None, chon: str | None) -> KetQuaCham:
    """Chấm một câu. `chon` là chuỗi nhãn học sinh gửi ("B", "A,C", "Đ,S,Đ,S",
    "3,5"); rỗng = bỏ trống, vẫn chấm (là sai)."""
    dap_an = (dap_an or "").strip()
    chon = (chon or "").strip()
    if not dap_an:
        # Kho thiếu đáp án mà vẫn chấm thì mọi bài làm đều "sai" — lỗi dữ liệu
        # của kho đổ lên đầu học sinh.
        return _KHONG_CHAM

    if dang == "TN1":
        return KetQuaCham(True, tach_khoa(chon)[:1] == tach_khoa(dap_an)[:1])

    if dang == "TNN":
        # Đúng ĐỦ mọi phương án mới có điểm — thiếu hay thừa một cái đều sai.
        return KetQuaCham(True, set(tach_khoa(chon)) == set(tach_khoa(dap_an)))

    if dang == "DS":
        dung_ = [x for x in _y_ds(dap_an) if x]
        chon_ = _y_ds(chon)
        so = sum(1 for i, d in enumerate(dung_) if i < len(chon_) and chon_[i] == d)
        return KetQuaCham(True, so == len(dung_), so_y_dung=so, so_y=len(dung_))

    if dang == "DSN":
        # Đáp số là ảnh hoặc nhiều dòng: testbank nói rõ là không chấm tự động.
        if co_anh(dap_an) or "\n" in dap_an:
            return _KHONG_CHAM
        return KetQuaCham(True, bool(chon) and _chuan_dsn(chon) == _chuan_dsn(dap_an))

    # TL (giáo viên chấm) và mọi dạng lạ: không đoán.
    return _KHONG_CHAM

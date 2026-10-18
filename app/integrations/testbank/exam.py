"""Rút đề — `POST /exams:preview` của exam-service.

Chỉ XEM TRƯỚC: đề không lưu bên testbank, không trừ hạn mức của ai. Kết quả chỉ
có QID + mã (mức độ, dạng thức, YCCĐ), KHÔNG có đề bài — lấy ở `noi_dung.py`.

Thiếu câu thì testbank BÁO THIẾU chứ không lấy mức khác bù (`is_complete`,
`shortage`, `message`). Bên mình phải hiện thông báo đó cho học sinh, đừng lặng
lẽ đưa ra một đề ngắn hơn số câu đã hứa.
"""
from dataclasses import dataclass, field

from app.integrations.testbank.client import TestbankClient

#: Tỉ lệ Biết / Hiểu / Vận dụng. Là TRỌNG SỐ, không phải phần trăm — testbank
#: chia theo phần dư lớn nhất: 12 câu -> B5 / H4 / V3.
TI_LE_MAC_DINH = {"B": 40, "H": 30, "V": 30}


@dataclass(frozen=True)
class CauRut:
    thu_tu: int
    qid: str
    ar_id: str
    muc_do: str          # B | H | V
    dang: str            # TN1 | TNN | DS | DSN | TL


@dataclass(frozen=True)
class DeRut:
    is_complete: bool
    message: str
    quota: dict[str, int] = field(default_factory=dict)
    shortage: dict[str, int] = field(default_factory=dict)
    items: list[CauRut] = field(default_factory=list)


async def rut_de(
    tb: TestbankClient, *, subject: str, grade: str, exam: str | None, total: int,
    ar_ids: list[str] | None = None, seed: int = 0,
    ratio: dict[str, int] | None = None,
) -> DeRut:
    """Cùng ma trận + cùng `seed` -> cùng đề. `ar_ids` giới hạn trong các YCCĐ
    này (đề "làm lại chỗ còn yếu"); None/rỗng = mọi YCCĐ của kỳ."""
    body = {
        "subject": subject, "grade": grade,
        # Tên trường là `exam`, KHÔNG phải `exam_code` (đính chính của testbank):
        # trường lạ bị bỏ qua im lặng, gửi sai tên là rút trên mọi kỳ.
        "exam": exam, "total": total, "ratio": ratio or TI_LE_MAC_DINH,
        "spread_ar": True, "seed": seed,
        # Rỗng thì gửi null: `[]` dễ bị hiểu là "không YCCĐ nào" -> đề rỗng.
        "ar_ids": list(ar_ids) if ar_ids else None,
    }
    d = await tb.goi("exam", "/exams:preview", body)
    return DeRut(
        is_complete=bool(d.get("is_complete")),
        message=str(d.get("message") or ""),
        quota=dict(d.get("quota") or {}),
        shortage=dict(d.get("shortage") or {}),
        items=[CauRut(thu_tu=int(i.get("ordinal") or n), qid=i["qid"], ar_id=i.get("ar_id") or "",
                      muc_do=i.get("difficulty_code") or "", dang=i.get("format_code") or "")
               for n, i in enumerate(d.get("items") or [], start=1)],
    )

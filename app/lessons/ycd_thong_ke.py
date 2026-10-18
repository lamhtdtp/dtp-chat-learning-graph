"""Thống kê kết quả làm bài theo YÊU CẦU CẦN ĐẠT.

Gom theo `QuizAttemptItem.ycd_key` chứ không theo đơn vị kiến thức. Khác biệt
không nhỏ: một đơn vị có nhiều YCCĐ, học sinh có thể vững phần này mà hổng phần
kia, mà "trượt bài kiểm tra của Bài 11" thì không nói được em hổng chỗ nào.

Đây là đầu vào của hai việc:
  * hiện hồ sơ học tập theo YCCĐ (GET /lessons/me/ycd);
  * chọn `ar_ids` khi rút đề mới từ DTP Testbank — "làm lại đúng chỗ còn yếu".
"""
from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import QuizAttempt, QuizAttemptItem


@dataclass(frozen=True)
class ThongKeYcd:
    ycd_key: str
    ycd_text: str
    ar_id: str | None
    dung: int
    tong: int

    @property
    def ti_le(self) -> float:
        """Tỉ lệ đúng trong khoảng 0..1. `tong` không bao giờ là 0 (chỉ có dòng
        khi đã làm ít nhất một câu), nhưng vẫn chặn để không chia 0."""
        return self.dung / self.tong if self.tong else 0.0


async def theo_ycd(
    session: AsyncSession, user_id: int, *, gan_day: int | None = None
) -> list[ThongKeYcd]:
    """Đúng/tổng theo từng YCCĐ của một học sinh, nhiều câu nhất lên trước.

    `gan_day` giới hạn trong N lần nộp gần nhất — mặc định tính cả lịch sử. Có
    giới hạn thì gợi ý bám theo trình độ HIỆN TẠI: em đã sửa được lỗi từ tháng
    trước mà vẫn bị gợi ý ôn lại chỗ đó là phản tác dụng.

    Bỏ qua dòng có `ycd_key` rỗng (câu sinh từ trước khi quiz_json có trường
    `ycd`): không gom theo YCCĐ được thì đếm vào cũng chỉ làm sai con số.
    """
    dieu_kien = [QuizAttempt.user_id == user_id, QuizAttemptItem.ycd_key != ""]
    if gan_day is not None:
        gan_nhat = (
            select(QuizAttempt.id)
            .where(QuizAttempt.user_id == user_id)
            .order_by(QuizAttempt.created_at.desc(), QuizAttempt.id.desc())
            .limit(gan_day)
        )
        dieu_kien.append(QuizAttemptItem.attempt_id.in_(gan_nhat))

    rows = (await session.execute(
        select(
            QuizAttemptItem.ycd_key,
            func.max(QuizAttemptItem.ycd_text),
            func.max(QuizAttemptItem.ar_id),
            func.sum(case((QuizAttemptItem.dung, 1), else_=0)),
            func.count(),
        )
        .join(QuizAttempt, QuizAttempt.id == QuizAttemptItem.attempt_id)
        .where(*dieu_kien)
        .group_by(QuizAttemptItem.ycd_key)
        .order_by(func.count().desc(), QuizAttemptItem.ycd_key)
    )).all()

    return [
        ThongKeYcd(ycd_key=k, ycd_text=txt or "", ar_id=ar, dung=int(dung or 0), tong=int(tong))
        for k, txt, ar, dung, tong in rows
    ]


#: Dưới tỉ lệ này thì coi là chưa vững — cùng ngưỡng đạt của bài kiểm tra nhanh
#: (`_NGUONG_DAT` trong app/api/lessons.py), để hai chỗ không nói ngược nhau.
NGUONG_DAT = 0.7
#: Số câu tối thiểu mới dám kết luận. Sai 1/1 câu không phải "hổng kiến thức",
#: đó là một câu sai — gợi ý ôn lại cả một yêu cầu cần đạt vì một câu duy nhất
#: là làm phiền học sinh bằng dữ liệu mỏng.
TOI_THIEU = 2


def la_yeu(r: ThongKeYcd, *, nguong: float = NGUONG_DAT, toi_thieu: int = TOI_THIEU) -> bool:
    """Một YCCĐ có đang yếu không. Dùng chung cho cả hồ sơ học tập lẫn việc chọn
    `ar_ids` — ngưỡng nằm một chỗ thì giao diện và đề ôn tập không lệch nhau."""
    return r.tong >= toi_thieu and r.ti_le < nguong


def con_yeu(
    rows: list[ThongKeYcd], *, nguong: float = NGUONG_DAT,
    toi_thieu: int = TOI_THIEU, toi_da: int = 5,
) -> list[ThongKeYcd]:
    """Lọc ra các YCCĐ còn yếu, yếu nhất lên đầu.

    `toi_da` giữ danh sách đủ ngắn để còn ra được một đề ôn tập có nghĩa: trải 12
    câu lên 8 YCCĐ thì mỗi chỗ một câu rưỡi, không ôn được gì.
    """
    yeu = [r for r in rows if la_yeu(r, nguong=nguong, toi_thieu=toi_thieu)]
    # Yếu nhất trước; cùng tỉ lệ thì ưu tiên chỗ có nhiều câu hơn (chắc chắn hơn);
    # rồi tới ycd_key để hai lần gọi liên tiếp cho ra cùng thứ tự.
    yeu.sort(key=lambda r: (r.ti_le, -r.tong, r.ycd_key))
    return yeu[:toi_da]


def chon_ar_on_lai(
    lich_su: list[ThongKeYcd], lan_nay: list[tuple[str, int, int]], *, toi_da: int = 5,
) -> list[str]:
    """Mã YCCĐ bên testbank (`ar_id`) cho "bài làm mới" — yếu nhất lên đầu.

    Hai nguồn, theo thứ tự:
      1. Lịch sử (`con_yeu`) — chắc chắn hơn vì đủ số câu mới kết luận.
      2. Bài VỪA làm: YCCĐ nào còn sai. Cần vì đề cuối kỳ 12 câu thường trải
         trên 12 YCCĐ, mỗi chỗ một câu, nên ở lần làm đầu lịch sử chưa chỗ nào
         đủ `TOI_THIEU` câu — chỉ dựa vào (1) thì nút "làm bài mới" trống trơn.

    `lan_nay`: (ar_id, đúng, tổng) của bài vừa nộp. Bỏ YCCĐ không có `ar_id`
    (câu tự sinh trong bài học — testbank không biết YCCĐ đó là gì).
    """
    out: list[str] = []
    for r in con_yeu(lich_su, toi_da=toi_da):
        if r.ar_id and r.ar_id not in out:
            out.append(r.ar_id)
    sai = sorted((x for x in lan_nay if x[0] and x[1] < x[2]),
                 key=lambda x: (x[1] / x[2], -x[2], x[0]))
    for ar, _d, _t in sai:
        if ar not in out:
            out.append(ar)
    return out[:toi_da]

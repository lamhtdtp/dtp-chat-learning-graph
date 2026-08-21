"""Phiên học: ghi thời lượng + đọc số cho Hồ sơ học tập (REQ §3.6).

Client ping mỗi ~30s khi tab ĐANG HIỆN. Server cộng dồn vào phiên đang mở của
đúng (user, topic), hoặc mở phiên mới nếu đã nghỉ quá `_KHOANG_MOI`.

Vì sao cộng dồn ở server chứ không tin tổng client gửi: client gửi tổng thì mở
devtools là tự khai 10 tiếng học. Server chỉ nhận "vừa học thêm k giây" và tự
chặn trần theo khoảng ping.
"""
import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StudySession
from app.lessons import bo_cuc

# Nghỉ quá 10 phút -> coi là phiên MỚI. Không tách thì một buổi tối mở tab rồi
# quay lại sáng mai sẽ thành một phiên 12 tiếng.
_KHOANG_MOI = timedelta(minutes=10)
# Trần mỗi lần ping. Client ping 30s/lần; cho phép trễ tới 2 phút rồi chặn — ping
# khai 3600 giây một lần là dấu hiệu bị sửa, không phải học thật.
_TRAN_PING = 120
MUC_TIEU_PHUT = 20   # mục tiêu/ngày, dùng cho đường nét đứt trên biểu đồ


async def ping(session: AsyncSession, user_id: int, topic_id: int, giay: int,
               phan_doc: list[str] | None = None) -> StudySession:
    """Cộng `giay` + HỢP NHẤT phần đã đọc vào phiên đang mở. KHÔNG commit.

    `phan_doc` hợp nhất (union) chứ không ghi đè: client gửi "các phần đang thấy
    là đã đọc", cuộn lên trên thì danh sách ngắn lại — ghi đè là mất phần đã đọc
    trước đó."""
    giay = max(0, min(int(giay or 0), _TRAN_PING))
    now = datetime.now()
    ph = await session.scalar(
        select(StudySession).where(StudySession.user_id == user_id,
                                   StudySession.topic_id == topic_id)
        .order_by(StudySession.dong_luc.desc()).limit(1))
    if ph is None or (now - ph.dong_luc) > _KHOANG_MOI:
        ph = StudySession(user_id=user_id, topic_id=topic_id, so_giay=giay,
                          phan_doc_json=json.dumps(_loc_phan(phan_doc), ensure_ascii=False))
        session.add(ph)
        return ph
    ph.so_giay = (ph.so_giay or 0) + giay
    ph.dong_luc = now
    if phan_doc:
        ph.phan_doc_json = json.dumps(
            _loc_phan(doc_phan(ph) + list(phan_doc)), ensure_ascii=False)
    return ph


def _loc_phan(ds: list[str] | None) -> list[str]:
    """Lược id phần lạ + khử trùng, GIỮ thứ tự chuẩn. Không lọc thì client gửi gì
    cũng vào DB và mẫu số "/y phần" tính sai."""
    co = set(ds or []) & set(bo_cuc.IDS)
    return [p for p in bo_cuc.IDS if p in co]


def doc_phan(ph: StudySession) -> list[str]:
    """Phần đã đọc của một phiên. Dữ liệu rác -> rỗng, không làm sập hồ sơ."""
    try:
        ds = json.loads(ph.phan_doc_json or "[]")
        return [x for x in ds if isinstance(x, str)]
    except json.JSONDecodeError:
        return []


def dang_hoc(ph: StudySession) -> bool:
    """Phiên còn đang mở? Dùng cho nhãn "● đang học" (§3.6)."""
    return (datetime.now() - ph.dong_luc) <= _KHOANG_MOI


async def them_cau_hoi(session: AsyncSession, user_id: int, topic_id: int) -> None:
    """+1 câu hỏi trợ lý vào phiên đang mở (nếu có). KHÔNG mở phiên mới: hỏi mà
    chưa từng đọc bài thì không phải một phiên học."""
    ph = await session.scalar(
        select(StudySession).where(StudySession.user_id == user_id,
                                   StudySession.topic_id == topic_id)
        .order_by(StudySession.dong_luc.desc()).limit(1))
    if ph is not None and (datetime.now() - ph.dong_luc) <= _KHOANG_MOI:
        ph.so_hoi = (ph.so_hoi or 0) + 1


async def thoi_gian(session: AsyncSession, user_id: int, ngay: int = 14) -> dict:
    """Số liệu 4 ô + biểu đồ `ngay` ngày + lịch sử phiên (§3.6 khối 1–3)."""
    hom_nay = date.today()
    tu = hom_nay - timedelta(days=ngay - 1)

    tong, so_phien = (await session.execute(
        select(func.coalesce(func.sum(StudySession.so_giay), 0), func.count())
        .where(StudySession.user_id == user_id))).one()

    async def _sum(tu_ngay: date) -> int:
        return await session.scalar(
            select(func.coalesce(func.sum(StudySession.so_giay), 0))
            .where(StudySession.user_id == user_id,
                   func.date(StudySession.mo_luc) >= tu_ngay)) or 0

    giay_hom_nay = await _sum(hom_nay)
    giay_7 = await _sum(hom_nay - timedelta(days=6))

    rows = (await session.execute(
        select(func.date(StudySession.mo_luc).label("d"),
               func.coalesce(func.sum(StudySession.so_giay), 0))
        .where(StudySession.user_id == user_id, func.date(StudySession.mo_luc) >= tu)
        .group_by("d"))).all()
    theo_ngay = {str(d): int(g) for d, g in rows}
    # Ngày không học vẫn phải có mặt với 0 — thiếu điểm thì biểu đồ nối tắt và
    # trông như ngày đó vẫn học.
    bieu_do = [{"ngay": str(tu + timedelta(days=i)),
                "phut": round(theo_ngay.get(str(tu + timedelta(days=i)), 0) / 60),
                "hom_nay": (tu + timedelta(days=i)) == hom_nay}
               for i in range(ngay)]

    return {
        "hom_nay_phut": round(giay_hom_nay / 60),
        "bay_ngay_phut": round(giay_7 / 60),
        "tong_phut": round(int(tong) / 60),
        "so_phien": int(so_phien),
        "muc_tieu_phut": MUC_TIEU_PHUT,
        "dat_muc_tieu": round(giay_hom_nay / 60) >= MUC_TIEU_PHUT,
        "bieu_do": bieu_do,
    }

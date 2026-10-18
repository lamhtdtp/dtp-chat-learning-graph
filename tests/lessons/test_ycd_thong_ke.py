"""Thống kê theo yêu cầu cần đạt — nền cho "bài làm mới chọn theo YCCĐ"."""
import pytest
from sqlalchemy import select

from app.db.models import (
    CurriculumTopic, Grade, QuizAttempt, QuizAttemptItem, Subject, User,
)
from app.lessons import ycd_thong_ke as tk
from app.lessons.ycd_key import chuan_hoa

YCD_A = "Vận dụng được dấu hiệu chia hết cho 2, 5, 3, 9"
YCD_B = "Xác định được ƯCLN, BCNN của hai số tự nhiên"


def _tk(ycd: str, dung: int, tong: int) -> tk.ThongKeYcd:
    return tk.ThongKeYcd(ycd_key=chuan_hoa(ycd), ycd_text=ycd, ar_id=None, dung=dung, tong=tong)


# ─── con_yeu / la_yeu: thuần tính toán, không cần CSDL ────────────────────────

def test_du_cau_va_duoi_nguong_thi_la_yeu():
    assert tk.la_yeu(_tk(YCD_A, dung=1, tong=4))


def test_dat_nguong_thi_khong_yeu():
    assert not tk.la_yeu(_tk(YCD_A, dung=7, tong=10))     # 0.7 là ĐẠT, không phải yếu


def test_mot_cau_sai_chua_du_ket_luan():
    """Sai 1/1 không phải "hổng kiến thức" — gợi ý ôn lại cả một yêu cầu cần đạt
    vì một câu duy nhất là làm phiền học sinh bằng dữ liệu mỏng."""
    assert not tk.la_yeu(_tk(YCD_A, dung=0, tong=1))


def test_yeu_nhat_len_dau():
    rows = [_tk(YCD_A, 3, 5), _tk(YCD_B, 0, 4)]
    assert [r.ycd_text for r in tk.con_yeu(rows)] == [YCD_B, YCD_A]


def test_cung_ti_le_thi_nhieu_cau_hon_len_truoc():
    """Cùng 50% nhưng 2/4 chắc chắn hơn 1/2 — ưu tiên chỗ có nhiều bằng chứng."""
    it_cau, nhieu_cau = _tk("YCD it", 1, 2), _tk("YCD nhieu", 2, 4)
    assert tk.con_yeu([it_cau, nhieu_cau])[0].ycd_text == "YCD nhieu"


def test_cat_bot_cho_de_on_tap_con_nghia():
    """Trải 12 câu lên 8 YCCĐ thì mỗi chỗ một câu rưỡi, không ôn được gì."""
    rows = [_tk(f"YCD {i}", 0, 3) for i in range(8)]
    assert len(tk.con_yeu(rows)) == 5


def test_hai_lan_goi_cho_cung_thu_tu():
    rows = [_tk(f"YCD {i}", 1, 4) for i in range(5)]
    assert [r.ycd_text for r in tk.con_yeu(rows)] == [r.ycd_text for r in tk.con_yeu(list(reversed(rows)))]


# ─── theo_ycd: gom từ CSDL ───────────────────────────────────────────────────

@pytest.fixture
async def hoc_sinh_va_bai(db_session):
    """Một học sinh + một đơn vị kiến thức, đủ để treo QuizAttempt vào."""
    subject = await db_session.scalar(select(Subject).limit(1))
    grade = await db_session.scalar(select(Grade).limit(1))
    if subject is None or grade is None:
        pytest.skip("CSDL chưa có môn/khối — chạy seed trước")
    topic = await db_session.scalar(
        select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id).limit(1))
    if topic is None:
        pytest.skip("CSDL chưa có đơn vị kiến thức — chạy seed trước")
    user = User(email="tk-ycd@test.local", password_hash="x", name="HS thống kê", role="student")
    db_session.add(user)
    await db_session.flush()
    return user, topic


async def _nop(db_session, user, topic, cac_cau: list[tuple[str, bool]]) -> QuizAttempt:
    """Một lần nộp với danh sách (nguyên văn YCCĐ, đúng/sai)."""
    dung = sum(1 for _, d in cac_cau if d)
    at = QuizAttempt(user_id=user.id, topic_id=topic.id,
                     diem=dung, tong=len(cac_cau), dat=dung / len(cac_cau) >= 0.7)
    db_session.add(at)
    await db_session.flush()
    for ycd, d in cac_cau:
        db_session.add(QuizAttemptItem(
            attempt_id=at.id, ycd_key=chuan_hoa(ycd), ycd_text=ycd, dung=d))
    await db_session.flush()
    return at


async def test_gom_theo_ycd_khong_theo_bai(db_session, hoc_sinh_va_bai):
    """Một đơn vị có nhiều YCCĐ: vững phần này mà hổng phần kia phải thấy được."""
    user, topic = hoc_sinh_va_bai
    await _nop(db_session, user, topic,
               [(YCD_A, True), (YCD_A, True), (YCD_B, False), (YCD_B, False)])

    rows = {r.ycd_text: r for r in await tk.theo_ycd(db_session, user.id)}
    assert (rows[YCD_A].dung, rows[YCD_A].tong) == (2, 2)
    assert (rows[YCD_B].dung, rows[YCD_B].tong) == (0, 2)
    assert tk.la_yeu(rows[YCD_B]) and not tk.la_yeu(rows[YCD_A])


async def test_cong_don_qua_nhieu_lan_nop(db_session, hoc_sinh_va_bai):
    user, topic = hoc_sinh_va_bai
    await _nop(db_session, user, topic, [(YCD_A, True), (YCD_A, False)])
    await _nop(db_session, user, topic, [(YCD_A, False), (YCD_A, False)])

    (row,) = [r for r in await tk.theo_ycd(db_session, user.id) if r.ycd_text == YCD_A]
    assert (row.dung, row.tong) == (1, 4)


async def test_gan_day_chi_tinh_lan_nop_moi_nhat(db_session, hoc_sinh_va_bai):
    """Em đã sửa được lỗi từ lần trước mà vẫn bị gợi ý ôn lại là phản tác dụng."""
    user, topic = hoc_sinh_va_bai
    await _nop(db_session, user, topic, [(YCD_A, False), (YCD_A, False)])   # lần cũ: sai hết
    await _nop(db_session, user, topic, [(YCD_A, True), (YCD_A, True)])     # lần mới: đúng hết

    (moi,) = await tk.theo_ycd(db_session, user.id, gan_day=1)
    assert (moi.dung, moi.tong) == (2, 2)
    (ca_lich_su,) = await tk.theo_ycd(db_session, user.id)
    assert (ca_lich_su.dung, ca_lich_su.tong) == (2, 4)


async def test_bo_qua_cau_khong_co_ycd(db_session, hoc_sinh_va_bai):
    """Câu sinh trước khi quiz_json có trường `ycd` — gom theo YCCĐ không được
    thì đếm vào cũng chỉ làm sai con số."""
    user, topic = hoc_sinh_va_bai
    await _nop(db_session, user, topic, [(YCD_A, True), ("", False)])

    rows = await tk.theo_ycd(db_session, user.id)
    assert [(r.ycd_text, r.tong) for r in rows] == [(YCD_A, 1)]


async def test_khong_lan_sang_hoc_sinh_khac(db_session, hoc_sinh_va_bai):
    user, topic = hoc_sinh_va_bai
    nguoi_khac = User(email="tk-ycd-2@test.local", password_hash="x", name="HS khác", role="student")
    db_session.add(nguoi_khac)
    await db_session.flush()
    await _nop(db_session, nguoi_khac, topic, [(YCD_A, False), (YCD_A, False)])

    assert await tk.theo_ycd(db_session, user.id) == []


async def test_xoa_lan_nop_thi_chi_tiet_di_theo(db_session, hoc_sinh_va_bai):
    """ondelete=CASCADE: chi tiết từng câu không có nghĩa khi đứng rời lần nộp."""
    user, topic = hoc_sinh_va_bai
    at = await _nop(db_session, user, topic, [(YCD_A, True)])

    await db_session.delete(at)
    await db_session.flush()

    con_lai = await db_session.scalars(
        select(QuizAttemptItem).filter_by(attempt_id=at.id))
    assert con_lai.all() == []

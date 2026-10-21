"""US-27 — test BỔ SUNG của QC sau khi DEV xong (lượt B), bám các lỗ hổng chưa có test ở lượt RED:

* mở lại kết quả cũ không bị "trượt cửa sổ 5 lần nộp" (hợp đồng §4 + điểm tự chọn của DEV: `den_attempt_id`);
* `de_xuat` không bao giờ nằm trong `ket_qua_json` đã lưu (Q11: kho đổi thì lần mở sau phải thấy bản mới);
* mã DOM an toàn: web không đưa nhãn / đường dẫn học liệu qua `dangerouslySetInnerHTML` (nhãn do quản trị
  nhập, người xem là học sinh) và link ngoài chỉ nhận http/https;
* NFR "khối Đề xuất cộng thêm ≤ 300 ms" với kho 2.000 học liệu — hàm chọn thuần + đọc kho từ DB.

Dùng lại hạ tầng của `test_de_xuat.py` / `de_xuat_khung.py`. Không gọi mạng / LLM.
"""
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("de_giao_cu_bat")  # US-26 đã ngừng: bật lại để dựng dữ liệu cũ
from sqlalchemy import select

from app.db.models import DeCuoiKy, HocLieu, QuizAttempt, QuizAttemptItem
from app.lessons import de_xuat as dx_svc
from app.lessons.ycd_key import chuan_hoa
from tests.api.de_xuat_khung import Cau, lam_bai, ma_cua, them_hl
from tests.api.test_de_xuat import (  # noqa: F401  (fixture dùng chung: tb, kho giả, chặn model, xoá cache)
    _khong_goi_model, _ma, _xoa_cache_ban_do_ar, canh, kho_dem, tb,
)

GOC = Path(__file__).resolve().parents[2]


async def test_mo_lai_ket_qua_cu_khong_doi_chua_vung_khi_da_lam_them_bai_khac(client, session, tb):
    """Vì sao: khối Đề xuất tính lại mỗi lần mở. Nếu "5 lần nộp gần nhất" trượt theo các bài làm SAU đó thì
    cùng một kết quả hôm nay nói "đúng nhưng chưa vững" (có học liệu Củng cố), mai nói "vững" (mất)."""
    the, gv, hs = await canh(client, session)
    # Lịch sử cũ: YCCĐ Y (the.ycds[0]) đúng 2/5 -> cộng bài này (2/2) = 4/7 < 80% => chưa vững.
    from tests.api.de_xuat_khung import chen_lich_su
    await chen_lich_su(session, hs.id, [[(the.ycds[0], d) for d in lan] for lan in [[True, False], [False], [True], [False]]])
    bttc = (await them_hl(client, gv, the, 0, loai="BTTC", muc_dich="cung_co", ma=_ma(the, "BTTC", "004")))["ma"]
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, [Cau(0), Cau(0), Cau(1, dung=False), Cau(1)])
    assert bttc in ma_cua(ket.de_xuat["doc_them"])

    # Sau đó em làm thêm 6 bài, Y đúng hết (giờ ở TƯƠNG LAI so với bài trên) -> trình độ HIỆN TẠI rất vững.
    tuong_lai = datetime(2099, 1, 1, 8, 0)
    for i in range(6):
        at = QuizAttempt(user_id=hs.id, topic_id=None, diem=3, tong=3, dat=True, nguon="cuoi_ky",
                         created_at=tuong_lai + timedelta(hours=i))
        session.add(at)
        await session.flush()
        for _ in range(3):
            session.add(QuizAttemptItem(attempt_id=at.id, ycd_key=chuan_hoa(the.ycds[0]), ycd_text=the.ycds[0],
                                        ar_id=None, qid=None, phan="kien_thuc", muc_do="B",
                                        chon="C", dap_an="C", dung=True))
    await session.commit()

    mo = (await ket.mo_lai())["ket_qua"]["de_xuat"]
    assert bttc in ma_cua(mo["doc_them"]), "mở lại kết quả cũ phải cho đúng khối Đề xuất của lúc đó"


async def test_de_xuat_khong_duoc_luu_vao_ket_qua_json(client, session, tb):
    """Vì sao: học liệu thêm / sửa / xoá thì lần mở sau phải thấy bản mới (Q11), và học liệu theo phương án
    chỉ được phép đi ra SAU khi chấm — lưu vào `ket_qua_json` là đóng băng bản cũ."""
    the, gv, hs = await canh(client, session)
    sgk = (await them_hl(client, gv, the, 0, loai="SGK", ma=_ma(the, "SGK", "007")))["ma"]
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, [Cau(0, dung=False), Cau(0), Cau(1), Cau(1)])
    assert sgk in ma_cua(ket.de_xuat["doc_them"])
    de = await session.scalar(select(DeCuoiKy).where(DeCuoiKy.id == ket.de_id))
    luu = json.loads(de.ket_qua_json)
    assert "de_xuat" not in luu
    assert sgk not in de.ket_qua_json and "bai_xuat_ban" not in de.ket_qua_json


# ── Hàm chọn thuần + đọc kho: hiệu năng với kho 2.000 học liệu (NFR 300 ms) ──
def _danh_muc_gia(n_ycd: int = 12) -> dx_svc.DanhMuc:
    return dx_svc.DanhMuc.tu_ds([
        dx_svc.MucYcd(ycd_key=f"ycd {i}", ycd_text=f"YCCĐ {i}", topic_id=1000 + i // 2,
                      don_vi=f"Bài {i // 2}", xuat_ban=True, rank=i) for i in range(n_ycd)])


def test_tinh_de_xuat_voi_2000_hoc_lieu_chay_duoi_300ms():
    """NFR US-27: dựng khối cộng thêm ≤ 300 ms (p95) với kho ≤ 2.000 học liệu. Phần thuần phải chiếm rất ít."""
    dm = _danh_muc_gia()
    cau = [dx_svc.CauKq(stt=i + 1, ycd_key=f"ycd {i % 12}", ycd_text=f"YCCĐ {i % 12}", dung=i % 3 != 0,
                        qid=f"Q-{i}", chon="A", dap_an="B", topic_id=1000 + (i % 12) // 2) for i in range(12)]
    kho = [{"ma": f"SGK-{i:05d}", "loai": ("VIDEO", "SGK", "SBT", "BTTC")[i % 4], "nhan": f"h{i}",
            "url": f"https://e.com/{i}", "muc_dich": "on_lai" if i % 5 else "cung_co",
            "ycd_key": f"ycd {i % 12}", "qid": f"Q-{i % 12}" if i % 7 == 0 else None,
            "option_key": "A" if i % 14 == 0 else None} for i in range(2000)]
    t = time.perf_counter()
    kq = dx_svc.tinh_de_xuat(cau, kho, dm, set())
    dt = time.perf_counter() - t
    assert kq["doc_them"] is not None
    assert dt < 0.3, f"tinh_de_xuat với 2.000 học liệu mất {dt:.3f}s"


async def test_doc_kho_hoc_lieu_2000_dong_duoi_300ms(session):
    """Đọc kho theo YCCĐ cần (có chỉ mục `ycd_key`) với 2.000 học liệu thật trong DB giao dịch của test."""
    import uuid
    u = uuid.uuid4().hex[:6].upper()
    session.add_all([HocLieu(ma=f"SGK-{u}-{i:04d}", loai="SGK", nhan=f"n{i}", url=f"https://e.com/{i}",
                             muc_dich="on_lai", ycd_key=f"ycd-{u}-{i % 40}", ycd_text=f"Y {i % 40}")
                     for i in range(2000)])
    await session.flush()
    t = time.perf_counter()
    ds = await dx_svc.doc_kho_hoc_lieu(session, [f"ycd-{u}-{k}" for k in range(5)])
    dt = time.perf_counter() - t
    assert len(ds) == 250
    assert dt < 0.3, f"doc_kho_hoc_lieu mất {dt:.3f}s"


# ── XSS: nhãn / đường dẫn học liệu do quản trị nhập, học sinh xem ──────────
@pytest.mark.parametrize("tep", ["web/src/learn/DeXuatView.tsx", "web-admin/src/admin/HocLieuView.tsx"])
def test_giao_dien_hoc_lieu_khong_dung_dangerously_set_inner_html(tep):
    """Nhãn học liệu là chữ tự do của quản trị viên (có thể là `<img onerror=…>`): chỉ được render dạng CHỮ
    (React tự thoát ký tự). Đưa qua HTML thô là XSS lưu trữ sang tài khoản học sinh."""
    src = (GOC / tep).read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML=" not in src and ".innerHTML" not in src   # lời chú thích được nhắc tên


def test_link_ngoai_chi_mo_khi_la_http_https_va_tach_khoi_trang_ket_qua():
    src = (GOC / "web/src/learn/DeXuatView.tsx").read_text(encoding="utf-8")
    assert re.search(r"\^https\?:\\/\\/", src), "thiếu lớp chặn scheme ở giao diện (lớp thứ hai sau máy chủ)"
    assert 'target="_blank"' in src and 'rel="noopener noreferrer"' in src

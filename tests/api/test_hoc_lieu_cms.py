"""US-27 (27a) — Kho học liệu có mã + CMS quản trị: Kịch bản 1–11. Viết TRƯỚC khi DEV code (RED).

Nguồn: User-Stories/EPIC-04-On-Tap/US-27-kho-hoc-lieu-va-de-xuat.md và hợp đồng
docs/contracts/US-27-kho-hoc-lieu-va-de-xuat.md (§1, §2, §7) ở repo tài liệu. Router mới: tiền tố
`/cms/hoc-lieu`. Toàn bộ `[tdd-core]`, không gọi LLM.

GIẢ ĐỊNH (hợp đồng chưa đặt tên — DEV làm theo hoặc báo QC đổi):
* KB 11: hàm kiểm độ phủ là `app.seed_hoc_lieu.kiem_do_phu(ycd_demo, hoc_lieu, *,
  video_phat_duoc)` -> dict có `dat: bool` và `thieu: list[str]` (rỗng khi đạt).
  `ycd_demo`: list nguyên văn YCCĐ của đề demo; `hoc_lieu`: list dict `{ma, loai, muc_dich,
  ycd, qid, option_key, url}` (`muc_dich` = "on_lai"|"cung_co", `qid`/`option_key` có thể None);
  `video_phat_duoc`: callable(url) -> bool, mặc định kiểm tệp video nội bộ có thật.
* Body CMS gửi `muc_dich` là "on_lai" | "cung_co".
* Đường dẫn "(để trống)" gửi `""`; "(không chọn)" YCCĐ gửi `""` hoặc bỏ khoá.
* `pham_vi` của danh sách: chữ "YCCĐ" ở đầu có thể là CHÍNH chữ "YCCĐ" hoặc nguyên văn YCCĐ
  (US ghi `"YCCĐ · câu Q-0123 · phương án B"`, hợp đồng không nói rõ) — test chấp nhận cả hai.

KHÔNG viết được (xem báo cáo): KB 3 "gửi đồng thời" thật (fixture `client` dùng chung một session
nên hai request song song làm hỏng nhau) — test hai lần liên tiếp + kiểm UNIQUE ở tầng DB;
phần giao diện của KB 1, 2 ("thông tin biểu mẫu vẫn được giữ"), 4 (chặn trên biểu mẫu), 10
("chuyển về trang đăng nhập", "không thấy màn quản trị") — Playwright ở lượt B.
"""
import re
import uuid

import pytest

pytestmark = pytest.mark.usefixtures("de_giao_cu_bat")  # US-26 đã ngừng: bật lại để dựng dữ liệu cũ
from sqlalchemy import text

from app.integrations.testbank.client import TestbankLoi
from app.lessons.ycd_key import chuan_hoa
from app.main import app
from app.api import cuoi_ky
from tests.api.de_xuat_khung import (
    Cau, TbGia, TheGioi, cau_tb, dung_the_gioi, lam_bai, lay_de_xuat, ma_cua, them_hl, tk,
)

MSG_BAN = "Kho đề đang bận, thử lại sau ít phút"


@pytest.fixture
def tb():
    gia = TbGia()
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    yield gia
    app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)


@pytest.fixture(autouse=True)
def _khong_goi_model(mocker):
    return mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value="{}"))


@pytest.fixture(autouse=True)
def _han_muc(mocker):
    return mocker.patch("app.llm.cache.incr_quota", mocker.AsyncMock(return_value=1))


def _body(the: TheGioi, **kv) -> dict:
    ma = f"VD-T{the.uid.upper()}-{uuid.uuid4().hex[:4].upper()}"
    return {"ma": ma, "loai": "VIDEO", "nhan": f"Nhãn {ma}",
            "url": "https://www.youtube.com/watch?v=abc123", "muc_dich": "on_lai",
            "ycd": the.ycds[0], **kv}


async def _ds(client, gv, **loc) -> list[dict]:
    r = await client.get("/cms/hoc-lieu", headers=gv.h, params=loc)
    assert r.status_code == 200, r.text
    return r.json()["hoc_lieu"]


def _la_nguoi(x, u) -> bool:
    """`nguoi_tao` / `nguoi_sua` nhận diện được người thao tác (tên, email hoặc id)."""
    raw = str(x)
    return bool(x) and (u.ten in raw or u.email in raw or str(u.id) in re.findall(r"\d+", raw))


# ═══ KB 1 — thêm học liệu hợp lệ ════════════════════════════════════════════
async def test_them_hoc_lieu_hop_le_hien_trong_danh_sach_kb1(client, session, tb):
    """KB1: đủ 6 thông tin, ghi người tạo + thời điểm; lọc theo YCCĐ thấy học liệu."""
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    b = _body(the, url="https://www.youtube.com/watch?v=abc123")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=b)
    assert r.status_code == 201, r.text

    ds = await _ds(client, gv, ycd=the.ycds[0])
    assert len(ds) == 1
    x = ds[0]
    assert (x["ma"], x["loai"], x["nhan"], x["url"], x["muc_dich"]) == (
        b["ma"], "VIDEO", b["nhan"], b["url"], "on_lai")
    assert x["ycd"] == the.ycds[0]
    assert _la_nguoi(x["nguoi_tao"], gv) and x["tao_luc"]


async def test_loc_theo_ycd_khong_phan_biet_hoa_thuong_khoang_trang_kb1(client, session, tb):
    """Lọc `ycd` theo khoá chuẩn hoá (hợp đồng §2), và không lẫn học liệu của YCCĐ khác."""
    the = await dung_the_gioi(session, (2,))
    gv = await tk(client, "giao_vien")
    mot = await them_hl(client, gv, the, 0)
    hai = await them_hl(client, gv, the, 1)
    ds = await _ds(client, gv, ycd="  " + the.ycds[0].upper() + "  ")
    assert [x["ma"] for x in ds] == [mot["ma"]]
    assert hai["ma"] not in [x["ma"] for x in ds]


async def test_danh_sach_moi_sua_truoc_va_loc_theo_loai_kb1(client, session, tb):
    the = await dung_the_gioi(session)
    gv = await tk(client, "admin")
    a = await them_hl(client, gv, the, 0, loai="SGK")
    b = await them_hl(client, gv, the, 0, loai="VIDEO")
    ds = await _ds(client, gv, ycd=the.ycds[0])
    assert [x["ma"] for x in ds] == [b["ma"], a["ma"]]            # mới nhất trước
    assert [x["ma"] for x in await _ds(client, gv, ycd=the.ycds[0], loai="SGK")] == [a["ma"]]


# ═══ KB 2 — mã trùng ════════════════════════════════════════════════════════
async def test_ma_trung_khac_hoa_thuong_bi_tu_choi_kb2(client, session, tb):
    """Mã so khớp CHỮ HOA: "vd-…" trùng "VD-…". Hai bản cùng mã làm học sinh thấy hai lần."""
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    b = _body(the)
    assert (await client.post("/cms/hoc-lieu", headers=gv.h, json=b)).status_code == 201
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json={**b, "ma": b["ma"].lower(),
                                                              "nhan": "Nhãn khác"})
    assert r.status_code == 409
    assert r.json()["detail"] == f"Mã {b['ma'].upper()} đã tồn tại"
    ds = await _ds(client, gv, ycd=the.ycds[0])
    assert [x["ma"] for x in ds] == [b["ma"].upper()] and ds[0]["nhan"] == b["nhan"]


async def test_ma_luu_chu_hoa_kb2(client, session, tb):
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    b = _body(the)
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json={**b, "ma": b["ma"].lower()})
    assert r.status_code == 201
    assert [x["ma"] for x in await _ds(client, gv, ycd=the.ycds[0])] == [b["ma"].upper()]


# ═══ KB 3 — thêm đồng thời cùng một mã ══════════════════════════════════════
async def test_hai_lan_them_lien_tiep_cung_ma_chi_mot_thanh_cong_kb3(client, session, tb):
    """KB3 (phần xác định được): lần hai bị 409 đúng thông báo. Phần "đồng thời thật" do UNIQUE
    ở DB gánh — xem test kế tiếp."""
    the = await dung_the_gioi(session)
    gv1, gv2 = await tk(client, "chuyen_gia"), await tk(client, "giao_vien")
    b = _body(the)
    r1 = await client.post("/cms/hoc-lieu", headers=gv1.h, json=b)
    r2 = await client.post("/cms/hoc-lieu", headers=gv2.h, json=b)
    assert sorted([r1.status_code, r2.status_code]) == [201, 409]
    assert r2.json()["detail"] == f"Mã {b['ma'].upper()} đã tồn tại"


async def test_db_co_unique_tren_cot_ma_kb3(session):
    """KB3: kiểm-rồi-chèn ở tầng ứng dụng thua cuộc đua; chốt cuối phải là UNIQUE trong DB
    trên đúng cột `ma` (hoặc `upper(ma)`) của bảng `hoc_lieu` (hợp đồng §1). Review kiểm thêm:
    IntegrityError phải được bắt và đổi thành 409, không thành 500."""
    rows = (await session.execute(text(
        "select indexdef from pg_indexes where tablename = 'hoc_lieu' and schemaname = current_schema()"
    ))).scalars().all()
    unique = [d for d in rows if "UNIQUE" in d.upper()]
    assert any("(ma)" in d or "upper(" in d.lower() for d in unique), (
        f"chưa có UNIQUE trên hoc_lieu.ma: {rows}")


# ═══ KB 4 — đường dẫn không hợp lệ ══════════════════════════════════════════
_DAI_1025 = "https://" + "a" * (1025 - len("https://"))
_DAI_1024 = "https://" + "a" * (1024 - len("https://"))
_URL_LOI = [
    ("", "Cần nhập đường dẫn"),
    ("www.youtube.com/watch?v=abc", "Đường dẫn phải bắt đầu bằng http:// hoặc https://"),
    ("javascript:alert(1)", "Đường dẫn phải bắt đầu bằng http:// hoặc https://"),
    ("ftp://may-chu/video.mp4", "Đường dẫn phải bắt đầu bằng http:// hoặc https://"),
    ("https://vi du.vn/video", "Đường dẫn không hợp lệ"),
    (_DAI_1025, "Đường dẫn dài tối đa 1024 ký tự"),
]


@pytest.mark.parametrize("url,thong_bao", _URL_LOI, ids=["trong", "thieu_giao_thuc", "javascript",
                                                         "ftp", "khoang_trang", "dai_1025"])
async def test_duong_dan_khong_hop_le_bi_tu_choi_kb4(client, session, tb, url, thong_bao):
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, url=url))
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == thong_bao
    assert await _ds(client, gv, ycd=the.ycds[0]) == []


async def test_duong_dan_http_https_hop_le_va_dai_dung_1024_kb4(client, session, tb):
    """Biên: đúng 1024 ký tự vẫn nhận; `http://` (không s) nhận."""
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    for url in (_DAI_1024, "http://may-chu.vn/video.mp4"):
        r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, url=url))
        assert r.status_code == 201, (url[:30], r.text)


@pytest.mark.parametrize("url", ["https://a.vn/\nx", "https://a.vn/x y",
                                 "data:text/html,<script>1</script>", "//evil.vn/x", "https://"])
async def test_duong_dan_la_khong_duoc_luu_kb4(client, session, tb, url):
    """Hệ thống không mở thử link, nên bộ lọc hình thức là hàng rào DUY NHẤT: không được để
    lọt khoảng trắng giữa chừng / xuống dòng, URL tương đối theo giao thức, `data:` hay URL rỗng sau
    giao thức vào kho (nó sẽ thành href cho học sinh bấm)."""
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, url=url))
    assert r.status_code == 422, (url, r.text)
    assert isinstance(r.json()["detail"], str)
    assert await _ds(client, gv, ycd=the.ycds[0]) == []


# ═══ KB 5 — trường bắt buộc / ngoài danh mục ════════════════════════════════
_TRUONG_LOI = [
    ("ma", "", "Cần nhập mã học liệu"),
    ("ma", "VD TO06 001", "Mã chỉ gồm chữ không dấu, số và dấu gạch ngang"),
    ("loai", "PDF", "Loại phải là VIDEO, SGK, SBT hoặc BTTC"),
    ("nhan", "", "Cần nhập nhãn"),
    ("nhan", "n" * 256, "Nhãn dài tối đa 255 ký tự"),
    ("muc_dich", "", "Chọn mục đích Ôn lại hoặc Củng cố"),
    ("ycd", "", "Cần gắn học liệu vào một yêu cầu cần đạt"),
]


@pytest.mark.parametrize("truong,gia_tri,thong_bao", _TRUONG_LOI,
                         ids=[f"{t}-{i}" for i, (t, _g, _m) in enumerate(_TRUONG_LOI)])
async def test_truong_khong_hop_le_bi_tu_choi_kb5(client, session, tb, truong, gia_tri, thong_bao):
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    b = _body(the)
    b[truong] = gia_tri
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=b)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == thong_bao


@pytest.mark.parametrize("truong,thong_bao", [
    ("ycd", "Cần gắn học liệu vào một yêu cầu cần đạt"),
    ("ma", "Cần nhập mã học liệu"),
    ("nhan", "Cần nhập nhãn"),
    ("url", "Cần nhập đường dẫn"),
    ("muc_dich", "Chọn mục đích Ôn lại hoặc Củng cố"),
])
async def test_thieu_han_khoa_van_ra_thong_bao_tieng_viet_kb5(client, session, tb, truong, thong_bao):
    """Biểu mẫu "không chọn" có thể là bỏ hẳn khoá: `detail` vẫn là CHUỖI tiếng Việt đúng chữ
    US, không phải danh sách lỗi của pydantic (hợp đồng §2)."""
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    b = _body(the)
    del b[truong]
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=b)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == thong_bao


async def test_nhan_dai_dung_255_duoc_nhan_kb5(client, session, tb):
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, nhan="n" * 255))
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("loai", ["VIDEO", "SGK", "SBT", "BTTC"])
async def test_bon_loai_hop_le_deu_nhan_kb5(client, session, tb, loai):
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, loai=loai))
    assert r.status_code == 201, r.text
    assert r.json()["loai"] == loai


# ═══ KB 6 — phạm vi gắn ═════════════════════════════════════════════════════
async def _the_gioi_co_cau(session, tb):
    """YCCĐ 0 có câu Q1 (4 phương án A–D); YCCĐ 1 có câu Q2."""
    the = await dung_the_gioi(session, (2,))
    tb.dat([cau_tb(the, 1, Cau(0)), cau_tb(the, 2, Cau(1))])
    return the


async def test_ycd_khong_co_trong_danh_muc_bi_tu_choi_kb6(client, session, tb):
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h,
                          json=_body(the, ycd=f"Yêu cầu không có trong ma trận {uuid.uuid4().hex}"))
    assert r.status_code == 422
    assert r.json()["detail"] == "Yêu cầu cần đạt không có trong danh mục"


async def test_ycd_khop_sau_chuan_hoa_van_nhan_kb6(client, session, tb):
    """Khoá nhận diện là nguyên văn ĐÃ CHUẨN HOÁ: dán thừa khoảng trắng / khác hoa thường vẫn gắn
    được, và lưu theo khoá chuẩn (lọc theo nguyên văn vẫn ra)."""
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h,
                          json=_body(the, ycd="  " + the.ycds[0].upper() + "  "))
    assert r.status_code == 201, r.text
    assert len(await _ds(client, gv, ycd=the.ycds[0])) == 1


async def test_ycd_khac_dau_cau_la_ycd_khac_kb6(client, session, tb):
    """Quy tắc khớp chép từ testbank: KHÔNG cắt dấu câu — thiếu dấu chấm là YCCĐ khác."""
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, ycd=the.ycds[0].rstrip(".")))
    assert r.status_code == 422
    assert r.json()["detail"] == "Yêu cầu cần đạt không có trong danh mục"


async def test_cau_thuoc_ycd_khac_bi_tu_choi_kb6(client, session, tb):
    the = await _the_gioi_co_cau(session, tb)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h,
                          json=_body(the, ycd=the.ycds[0], qid=the.qid(2)))
    assert r.status_code == 422
    assert r.json()["detail"] == "Câu này không thuộc yêu cầu cần đạt đã chọn"


async def test_phuong_an_ma_khong_chon_cau_bi_tu_choi_kb6(client, session, tb):
    the = await _the_gioi_co_cau(session, tb)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, option_key="B"))
    assert r.status_code == 422
    assert r.json()["detail"] == "Chọn câu trước khi gắn phương án"


async def test_phuong_an_khong_thuoc_cau_bi_tu_choi_kb6(client, session, tb):
    the = await _the_gioi_co_cau(session, tb)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h,
                          json=_body(the, qid=the.qid(1), option_key="E"))
    assert r.status_code == 422
    assert r.json()["detail"] == "Câu này không có phương án E"


async def test_phuong_an_chi_dung_muc_dich_on_lai_kb6(client, session, tb):
    the = await _the_gioi_co_cau(session, tb)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(
        the, qid=the.qid(1), option_key="B", muc_dich="cung_co"))
    assert r.status_code == 422
    assert r.json()["detail"] == "Học liệu gắn theo phương án chỉ dùng mục đích Ôn lại"


async def test_gan_theo_cau_khong_phuong_an_van_cho_cung_co_kb6(client, session, tb):
    """Biên của luật trên: chỉ gắn theo PHƯƠNG ÁN mới bị cấm Củng cố; gắn theo YCCĐ hay theo câu thì được."""
    the = await _the_gioi_co_cau(session, tb)
    gv = await tk(client, "chuyen_gia")
    for kv in ({}, {"qid": the.qid(1)}):
        r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, muc_dich="cung_co", **kv))
        assert r.status_code == 201, (kv, r.text)


async def test_cau_khong_ton_tai_trong_kho_bi_tu_choi_kb6(client, session, tb):
    """Hợp đồng chưa nêu chữ thông báo cho "mã câu không có trong kho đề" — test chỉ đòi từ chối
    4xx với `detail` là chuỗi, không tạo học liệu (đề xuất BA bổ sung câu chữ)."""
    the = await _the_gioi_co_cau(session, tb)
    gv = await tk(client, "chuyen_gia")
    r = await client.post("/cms/hoc-lieu", headers=gv.h,
                          json=_body(the, qid=f"Q-KHONG-CO-{uuid.uuid4().hex[:6]}"))
    assert 400 <= r.status_code < 500 and r.status_code != 409, r.text
    assert isinstance(r.json()["detail"], str)
    assert await _ds(client, gv, ycd=the.ycds[0]) == []


async def test_kiem_cau_goi_testbank_khong_xin_dap_an_kb6(client, session, tb):
    """Hợp đồng §2: kiểm câu bằng `questions:resolve` KHÔNG đáp án — CMS không cần và không được
    kéo đáp án / lời giải về máy chủ chỉ để kiểm phương án."""
    the = await _the_gioi_co_cau(session, tb)
    gv = await tk(client, "chuyen_gia")
    await them_hl(client, gv, the, 0, qid=the.qid(1), option_key="B")
    resolve = [b for (_d, duong, b) in tb.goi_list if duong == "/questions:resolve"]
    assert resolve, "chưa hỏi testbank để kiểm câu"
    assert all(not b.get("include_answers") for b in resolve)


async def test_testbank_loi_khi_kiem_cau_thanh_503_khong_tao_kb6(client, session, tb):
    the = await _the_gioi_co_cau(session, tb)
    gv = await tk(client, "chuyen_gia")
    tb.loi = TestbankLoi("mạng", tam_thoi=True)
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, qid=the.qid(1)))
    assert r.status_code == 503 and r.json()["detail"] == MSG_BAN
    tb.loi = None
    assert await _ds(client, gv, ycd=the.ycds[0]) == []


async def test_gan_theo_ycd_khong_can_hoi_testbank_kb6(client, session, tb):
    """Không có `qid` thì không có lý do gọi kho đề: testbank chết cũng không chặn việc thêm học liệu."""
    the = await dung_the_gioi(session)
    gv = await tk(client, "chuyen_gia")
    tb.loi = TestbankLoi("mạng", tam_thoi=True)
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the))
    assert r.status_code == 201, r.text
    assert tb.goi_list == [] and tb.lay_list == []


# ═══ KB 7 — gắn theo câu và phương án ═══════════════════════════════════════
async def test_gan_theo_cau_va_phuong_an_thanh_cong_kb7(client, session, tb):
    the = await _the_gioi_co_cau(session, tb)
    gv = await tk(client, "chuyen_gia")
    b = _body(the, qid=the.qid(1), option_key="B")
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=b)
    assert r.status_code == 201, r.text
    x = (await _ds(client, gv, ycd=the.ycds[0]))[0]
    assert (x["qid"], x["option_key"]) == (the.qid(1), "B")
    assert x["pham_vi"] in (f"YCCĐ · câu {the.qid(1)} · phương án B",
                            f"{the.ycds[0]} · câu {the.qid(1)} · phương án B")


async def test_pham_vi_hien_dung_theo_tung_muc_gan_kb7(client, session, tb):
    the = await _the_gioi_co_cau(session, tb)
    gv = await tk(client, "chuyen_gia")
    a = await them_hl(client, gv, the, 0)
    b = await them_hl(client, gv, the, 0, qid=the.qid(1))
    ds = {x["ma"]: x for x in await _ds(client, gv, ycd=the.ycds[0])}
    assert ds[a["ma"]]["pham_vi"] in ("YCCĐ", the.ycds[0])
    assert ds[b["ma"]]["pham_vi"] in (f"YCCĐ · câu {the.qid(1)}", f"{the.ycds[0]} · câu {the.qid(1)}")


# ═══ KB 8 — sửa học liệu ════════════════════════════════════════════════════
async def test_sua_hoc_lieu_ghi_nguoi_sua_va_khong_sua_ma_kb8(client, session, tb):
    the = await dung_the_gioi(session)
    gv, ad = await tk(client, "giao_vien"), await tk(client, "admin")
    hl = await them_hl(client, gv, the, 0, nhan="Video cũ")
    r = await client.patch(f"/cms/hoc-lieu/{hl['id']}", headers=ad.h, json={
        "nhan": "Thứ tự phép tính — ví dụ 2", "url": "https://www.youtube.com/watch?v=moi999"})
    assert r.status_code == 200, r.text
    x = (await _ds(client, ad, ycd=the.ycds[0]))[0]
    assert (x["nhan"], x["url"]) == ("Thứ tự phép tính — ví dụ 2", "https://www.youtube.com/watch?v=moi999")
    assert _la_nguoi(x["nguoi_sua"], ad) and x["sua_luc"]
    assert _la_nguoi(x["nguoi_tao"], gv)                            # người tạo giữ nguyên
    assert x["ma"] == hl["ma"]


@pytest.mark.parametrize("ma_moi", ["KHAC-0001", None])
async def test_gui_ma_khac_khi_sua_bi_tu_choi_kb8(client, session, tb, ma_moi):
    the = await dung_the_gioi(session)
    gv = await tk(client, "giao_vien")
    hl = await them_hl(client, gv, the, 0)
    moi = ma_moi or (hl["ma"][:-1] + ("A" if hl["ma"][-1] != "A" else "B"))
    r = await client.patch(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h, json={"ma": moi, "nhan": "x"})
    assert r.status_code == 422
    assert r.json()["detail"] == "Không sửa được mã học liệu"
    assert (await _ds(client, gv, ycd=the.ycds[0]))[0]["nhan"] == hl["nhan"]


async def test_gui_lai_dung_ma_cu_khi_sua_van_duoc_kb8(client, session, tb):
    """Biểu mẫu sửa gửi cả `ma` (khoá, không đổi) — chỉ khác mã hiện tại mới bị từ chối."""
    the = await dung_the_gioi(session)
    gv = await tk(client, "giao_vien")
    hl = await them_hl(client, gv, the, 0)
    r = await client.patch(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h,
                           json={"ma": hl["ma"], "nhan": "Nhãn mới"})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("truong,gia_tri,thong_bao", [
    ("url", "javascript:alert(1)", "Đường dẫn phải bắt đầu bằng http:// hoặc https://"),
    ("nhan", "", "Cần nhập nhãn"),
    ("loai", "PDF", "Loại phải là VIDEO, SGK, SBT hoặc BTTC"),
])
async def test_sua_cung_validation_nhu_them_kb8(client, session, tb, truong, gia_tri, thong_bao):
    """Sửa là cửa sau của mọi luật KB4–6: nếu PATCH không kiểm lại thì `javascript:` lọt vào qua đây."""
    the = await dung_the_gioi(session)
    gv = await tk(client, "giao_vien")
    hl = await them_hl(client, gv, the, 0)
    r = await client.patch(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h, json={truong: gia_tri})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == thong_bao
    x = (await _ds(client, gv, ycd=the.ycds[0]))[0]
    assert x[truong] == hl[truong]


async def test_sua_doi_phuong_an_sang_cung_co_bi_tu_choi_kb8(client, session, tb):
    """Cùng luật KB6 áp lúc sửa: học liệu gắn phương án không được đổi sang Củng cố."""
    the = await _the_gioi_co_cau(session, tb)
    gv = await tk(client, "giao_vien")
    hl = await them_hl(client, gv, the, 0, qid=the.qid(1), option_key="B")
    r = await client.patch(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h, json={"muc_dich": "cung_co"})
    assert r.status_code == 422
    assert r.json()["detail"] == "Học liệu gắn theo phương án chỉ dùng mục đích Ôn lại"


async def test_sua_hoc_lieu_khong_ton_tai_404_kb8(client, session, tb):
    gv = await tk(client, "giao_vien")
    r = await client.patch("/cms/hoc-lieu/987654321", headers=gv.h, json={"nhan": "x"})
    assert r.status_code == 404
    # 404 của "route chưa có" cũng ra "Not Found": đòi một thông báo tiếng Việt thật.
    assert r.json()["detail"] != "Not Found" and isinstance(r.json()["detail"], str)


async def test_hoc_sinh_thay_ban_moi_o_lan_xem_ket_qua_sau_kb8(client, session, tb):
    """KB8 + Q11: `de_xuat` tính theo kho HIỆN TẠI mỗi lần trả về, không đóng băng trong kết quả."""
    the = await dung_the_gioi(session)
    gv, hs = await tk(client, "chuyen_gia"), await tk(client)
    hl = await them_hl(client, gv, the, 0, nhan="Video cũ")
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, [Cau(0, dung=False), Cau(1)])
    assert lay_de_xuat(ket.kq)["video"]["hoc_lieu"][0]["nhan"] == "Video cũ"

    r = await client.patch(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h, json={
        "nhan": "Video mới", "url": "https://www.youtube.com/watch?v=moi"})
    assert r.status_code == 200, r.text
    m = lay_de_xuat(await ket.mo_lai())["video"]["hoc_lieu"][0]
    assert (m["nhan"], m["url"]) == ("Video mới", "https://www.youtube.com/watch?v=moi")


# ═══ KB 9 — xoá học liệu ════════════════════════════════════════════════════
async def test_xoa_hoc_lieu_xoa_mem_khoi_danh_sach_kb9(client, session, tb):
    the = await dung_the_gioi(session)
    gv = await tk(client, "giao_vien")
    hl = await them_hl(client, gv, the, 0)
    r = await client.delete(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h)
    assert r.status_code == 204
    assert await _ds(client, gv, ycd=the.ycds[0]) == []
    assert (await client.delete(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h)).status_code == 404
    assert (await client.patch(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h,
                               json={"nhan": "x"})).status_code == 404


async def test_ma_da_xoa_khong_dung_lai_duoc_kb9(client, session, tb):
    """Xoá MỀM: dòng còn đó nên mã không bao giờ dùng lại (bài cũ của học sinh khỏi trỏ nhầm sang
    học liệu khác mang cùng mã)."""
    the = await dung_the_gioi(session)
    gv = await tk(client, "giao_vien")
    hl = await them_hl(client, gv, the, 0)
    await client.delete(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h)
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=_body(the, ma=hl["ma"].lower()))
    assert r.status_code == 409
    assert r.json()["detail"] == f"Mã {hl['ma']} đã tồn tại"


async def test_xoa_hoc_lieu_bai_cu_va_bai_moi_khong_con_thay_kb9(client, session, tb):
    the = await dung_the_gioi(session)
    gv, an = await tk(client, "chuyen_gia"), await tk(client)
    giu = await them_hl(client, gv, the, 0, loai="SGK")
    hl = await them_hl(client, gv, the, 0, loai="VIDEO")
    cu = await lam_bai("cuoi_ky", client, session, tb, the, an, [Cau(0, dung=False), Cau(1)])
    assert hl["ma"] in ma_cua(cu.de_xuat["video"])

    assert (await client.delete(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h)).status_code == 204
    mo = lay_de_xuat(await cu.mo_lai())
    assert mo["video"] is None                                      # nhóm rỗng thì ẩn
    assert ma_cua(mo["doc_them"]) == [giu["ma"]]                    # học liệu khác vẫn còn
    moi = await lam_bai("cuoi_ky", client, session, tb, the, an, [Cau(0, dung=False), Cau(1)])
    assert hl["ma"] not in ma_cua(moi.de_xuat["video"]) + ma_cua(moi.de_xuat["doc_them"])


# ═══ KB 10 — phân quyền ═════════════════════════════════════════════════════
@pytest.mark.parametrize("vai", ["chuyen_gia", "giao_vien", "admin"])
async def test_ba_vai_quan_tri_duoc_xem_them_sua_xoa_kb10(client, session, tb, vai):
    the = await dung_the_gioi(session)
    u = await tk(client, vai)
    assert (await client.get("/cms/hoc-lieu", headers=u.h)).status_code == 200
    r = await client.post("/cms/hoc-lieu", headers=u.h, json=_body(the))
    assert r.status_code == 201, r.text
    hid = r.json()["id"]
    assert (await client.patch(f"/cms/hoc-lieu/{hid}", headers=u.h, json={"nhan": "đã sửa"})).status_code == 200
    assert (await client.delete(f"/cms/hoc-lieu/{hid}", headers=u.h)).status_code == 204


async def test_vai_nay_sua_xoa_duoc_hoc_lieu_cua_vai_khac_kb10(client, session, tb):
    """Q2: giáo viên sửa / xoá được học liệu của chuyên gia — không có khái niệm "của tôi"."""
    the = await dung_the_gioi(session)
    cg, gv = await tk(client, "chuyen_gia"), await tk(client, "giao_vien")
    hl = await them_hl(client, cg, the, 0)
    assert (await client.patch(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h, json={"nhan": "GV sửa"})).status_code == 200
    assert (await client.delete(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h)).status_code == 204


def _moi_duong(hid: int) -> list[tuple[str, str, dict | None]]:
    return [
        ("GET", "/cms/hoc-lieu", None),
        ("POST", "/cms/hoc-lieu", {}),
        ("PATCH", f"/cms/hoc-lieu/{hid}", {"nhan": "x"}),
        ("DELETE", f"/cms/hoc-lieu/{hid}", None),
        ("GET", "/cms/hoc-lieu/ycd", None),
        ("GET", "/cms/hoc-lieu/video-noi-bo", None),
        ("GET", "/cms/hoc-lieu/ma-ke-tiep?loai=VIDEO", None),
    ]


async def test_hoc_sinh_bi_tu_choi_moi_duong_cms_hoc_lieu_kb10(client, session, tb):
    the = await dung_the_gioi(session)
    gv, hs = await tk(client, "giao_vien"), await tk(client)
    hl = await them_hl(client, gv, the, 0)
    for method, path, body in _moi_duong(hl["id"]):
        r = await client.request(method, path, headers=hs.h, json=body)
        assert r.status_code == 403, (method, path, r.status_code)
    # Bị từ chối thì không được đổi gì.
    ds = await _ds(client, gv, ycd=the.ycds[0])
    assert [(x["ma"], x["nhan"]) for x in ds] == [(hl["ma"], hl["nhan"])]


async def test_chua_dang_nhap_bi_tu_choi_401_kb10(client, session, tb):
    the = await dung_the_gioi(session)
    gv = await tk(client, "giao_vien")
    hl = await them_hl(client, gv, the, 0)
    for method, path, body in _moi_duong(hl["id"]):
        r = await client.request(method, path, json=body)
        assert r.status_code == 401, (method, path, r.status_code)
    assert len(await _ds(client, gv, ycd=the.ycds[0])) == 1


async def test_hoc_sinh_khong_thay_hoc_lieu_qua_khoa_khac_kb10(client, session, tb):
    """Danh sách CMS chứa cả học liệu theo phương án (lộ đáp án) — học sinh gọi kèm bộ lọc cũng 403."""
    the = await _the_gioi_co_cau(session, tb)
    gv, hs = await tk(client, "giao_vien"), await tk(client)
    await them_hl(client, gv, the, 0, qid=the.qid(1), option_key="B")
    r = await client.get("/cms/hoc-lieu", headers=hs.h, params={"ycd": the.ycds[0], "q": "a"})
    assert r.status_code == 403
    assert "option_key" not in r.text and the.qid(1) not in r.text


# ═══ Danh mục chọn / video nội bộ / mã kế tiếp (hợp đồng §2) ═════════════════
async def test_danh_muc_ycd_theo_thu_tu_ma_tran_kb6(client, session, tb):
    the = await dung_the_gioi(session, (2, 1))
    gv = await tk(client, "giao_vien")
    r = await client.get("/cms/hoc-lieu/ycd", headers=gv.h)
    assert r.status_code == 200
    muc = [x for x in r.json()["ycd"] if x["ycd"] in the.ycds]
    assert [x["ycd"] for x in muc] == the.ycds                      # đúng thứ tự ma trận
    assert [x["ycd_key"] for x in muc] == [chuan_hoa(y) for y in the.ycds]
    assert muc[0]["don_vi"] == the.bai[0].ten and muc[0]["topic_id"] == the.bai[0].tid
    assert muc[2]["topic_id"] == the.bai[1].tid


async def test_video_noi_bo_chi_liet_ke_video_da_xong_kb4(client, session, tb):
    """Ghi chú KB4: video nội bộ chọn từ danh sách có sẵn — chỉ video ĐÃ XONG mới được chọn."""
    from app.db.models import VideoJob

    tag = uuid.uuid4().hex[:8]
    xong = VideoJob(concept_key=f"dx-xong-{tag}", sgk_version="v1", status="DONE",
                    video_url=f"/video/files/{tag}.mp4", title=f"Video xong {tag}")
    dang = VideoJob(concept_key=f"dx-dang-{tag}", sgk_version="v1", status="RENDERING",
                    video_url=None, title=f"Video đang dựng {tag}")
    hong = VideoJob(concept_key=f"dx-hong-{tag}", sgk_version="v1", status="FAILED",
                    video_url=None, title=f"Video hỏng {tag}")
    session.add_all([xong, dang, hong])
    await session.commit()
    gv = await tk(client, "giao_vien")
    r = await client.get("/cms/hoc-lieu/video-noi-bo", headers=gv.h)
    assert r.status_code == 200
    ds = [v for v in r.json()["video"] if tag in v["tieu_de"]]
    assert [v["tieu_de"] for v in ds] == [f"Video xong {tag}"]
    assert ds[0]["url"].split("?")[0] == f"/video/files/{tag}.mp4"


async def test_chon_video_noi_bo_luu_duoc_va_danh_dau_noi_bo_kb4(client, session, tb):
    """Video nội bộ không phải link http/https nhưng luôn hợp lệ (KB4 ghi chú); ở khối Đề xuất
    nó là `noi_bo: true`, còn URL ngoài (kể cả URL ngoài có đoạn `/video/files/`) thì `false`."""
    from app.db.models import VideoJob

    the = await dung_the_gioi(session)
    tag = uuid.uuid4().hex[:8]
    session.add(VideoJob(concept_key=f"dx-nb-{tag}", sgk_version="v1", status="DONE",
                         video_url=f"/video/files/{tag}.mp4", title=f"Video nội bộ {tag}"))
    await session.commit()
    gv, hs = await tk(client, "chuyen_gia"), await tk(client)
    nb = await them_hl(client, gv, the, 0, url=f"/video/files/{tag}.mp4", nhan="Nội bộ")
    ngoai = await them_hl(client, gv, the, 0, url=f"https://evil.example/video/files/{tag}.mp4",
                          nhan="Ngoài")
    ket = await lam_bai("cuoi_ky", client, session, tb, the, hs, [Cau(0, dung=False), Cau(1)])
    theo_ma = {m["ma"]: m for m in ket.de_xuat["video"]["hoc_lieu"]}
    assert theo_ma[nb["ma"]]["noi_bo"] is True
    assert theo_ma[ngoai["ma"]]["noi_bo"] is False


@pytest.mark.parametrize("loai,tien_to", [("VIDEO", "VD-"), ("SGK", "SGK-"), ("SBT", "SBT-"),
                                          ("BTTC", "BTTC-")])
async def test_goi_y_ma_ke_tiep_theo_tien_to_loai_q5(client, session, tb, loai, tien_to):
    gv = await tk(client, "giao_vien")
    r = await client.get(f"/cms/hoc-lieu/ma-ke-tiep?loai={loai}", headers=gv.h)
    assert r.status_code == 200
    assert re.fullmatch(re.escape(tien_to) + r"TO06-\d{3}", r.json()["ma"]), r.json()


async def test_ma_ke_tiep_tang_theo_so_lon_nhat_ke_ca_ma_da_xoa_q5(client, session, tb):
    the = await dung_the_gioi(session)
    gv = await tk(client, "giao_vien")
    n0 = int((await client.get("/cms/hoc-lieu/ma-ke-tiep?loai=VIDEO", headers=gv.h)).json()["ma"][-3:])
    assert n0 + 3 <= 999
    hl = await them_hl(client, gv, the, 0, ma=f"VD-TO06-{n0 + 3:03d}")
    ke = (await client.get("/cms/hoc-lieu/ma-ke-tiep?loai=VIDEO", headers=gv.h)).json()["ma"]
    assert ke == f"VD-TO06-{n0 + 4:03d}"
    await client.delete(f"/cms/hoc-lieu/{hl['id']}", headers=gv.h)
    ke2 = (await client.get("/cms/hoc-lieu/ma-ke-tiep?loai=VIDEO", headers=gv.h)).json()["ma"]
    assert ke2 == ke                                                # mã đã xoá vẫn chiếm số


# ═══ KB 11 — hàm kiểm độ phủ bộ dữ liệu demo ════════════════════════════════
def _kho_phu_du(n_ycd: int = 10) -> tuple[list[str], list[dict]]:
    ycd = [f"YCCĐ demo số {i}" for i in range(n_ycd)]
    hl: list[dict] = []
    for i, y in enumerate(ycd):
        hl.append({"ma": f"SGK-DEMO-{i:03d}", "loai": "SGK", "muc_dich": "on_lai", "ycd": y,
                   "qid": None, "option_key": None, "url": f"https://sgk.example/{i}"})
        hl.append({"ma": f"VD-DEMO-{i:03d}", "loai": "VIDEO", "muc_dich": "on_lai", "ycd": y,
                   "qid": None, "option_key": None, "url": f"/video/files/demo-{i}.mp4"})
    for i in range(3):
        hl.append({"ma": f"BTTC-DEMO-{i:03d}", "loai": "BTTC", "muc_dich": "cung_co", "ycd": ycd[i],
                   "qid": None, "option_key": None, "url": f"https://bttc.example/{i}"})
    for i in range(2):
        hl.append({"ma": f"VD-DEMO-PA-{i:03d}", "loai": "VIDEO", "muc_dich": "on_lai", "ycd": ycd[i],
                   "qid": f"Q-DEMO-{i}", "option_key": "B", "url": f"/video/files/pa-{i}.mp4"})
    return ycd, hl


def _kiem(ycd, hl, **kv):
    try:
        from app.seed_hoc_lieu import kiem_do_phu
    except ImportError as e:
        pytest.fail(f"app/seed_hoc_lieu.kiem_do_phu chưa có (hợp đồng §7): {e}")
    return kiem_do_phu(ycd, hl, video_phat_duoc=kv.get("video_phat_duoc", lambda url: True))


@pytest.mark.parametrize("n_ycd", [10, 11, 12])
def test_do_phu_dat_voi_bo_du_lieu_day_du_kb11(n_ycd):
    ycd, hl = _kho_phu_du(n_ycd)
    kq = _kiem(ycd, hl)
    assert kq["dat"] is True and kq["thieu"] == []


def _bo(hl, *, ma=()):
    """Bỏ các học liệu có mã trong `ma`."""
    return [h for h in hl if h["ma"] not in ma]


def test_thieu_sach_on_lai_cho_mot_ycd_khong_dat_kb11():
    ycd, hl = _kho_phu_du(10)
    kq = _kiem(ycd, _bo(hl, ma={"SGK-DEMO-009"}))
    assert kq["dat"] is False and kq["thieu"]


def test_hoc_lieu_cung_co_khong_thay_duoc_on_lai_kb11():
    """Mục đích Củng cố không tính vào "mỗi YCCĐ có ít nhất 1 học liệu Ôn lại"."""
    ycd, hl = _kho_phu_du(10)
    hl = [{**h, "muc_dich": "cung_co"} if h["ma"] == "SGK-DEMO-004" else h for h in hl]
    assert _kiem(ycd, hl)["dat"] is False


def test_chi_7_ycd_co_video_on_lai_khong_dat_kb11():
    ycd, hl = _kho_phu_du(10)
    bo = {f"VD-DEMO-{i:03d}" for i in (7, 8, 9)}
    kq = _kiem(ycd, _bo(hl, ma=bo))
    assert kq["dat"] is False and kq["thieu"]


def test_dung_8_ycd_co_video_on_lai_van_dat_kb11():
    ycd, hl = _kho_phu_du(10)
    bo = {f"VD-DEMO-{i:03d}" for i in (8, 9)}
    # YCCĐ 0,1 còn video theo phương án; 8 YCCĐ có video theo YCCĐ -> vẫn đủ 8.
    assert _kiem(ycd, _bo(hl, ma=bo))["dat"] is True


def test_chi_2_ycd_co_cung_co_khong_dat_kb11():
    ycd, hl = _kho_phu_du(10)
    kq = _kiem(ycd, _bo(hl, ma={"BTTC-DEMO-002"}))
    assert kq["dat"] is False and kq["thieu"]


def test_chi_1_cau_co_hoc_lieu_theo_phuong_an_khong_dat_kb11():
    ycd, hl = _kho_phu_du(10)
    kq = _kiem(ycd, _bo(hl, ma={"VD-DEMO-PA-001"}))
    assert kq["dat"] is False and kq["thieu"]


def test_hai_hoc_lieu_phuong_an_cung_mot_cau_chi_tinh_mot_cau_kb11():
    """"Ít nhất 2 CÂU": hai học liệu cùng gắn câu Q-DEMO-0 (phương án B và C) mới chỉ phủ một câu."""
    ycd, hl = _kho_phu_du(10)
    hl = [{**h, "qid": "Q-DEMO-0", "option_key": "C"} if h["ma"] == "VD-DEMO-PA-001" else h
          for h in hl]
    assert _kiem(ycd, hl)["dat"] is False


def test_video_noi_bo_khong_phat_duoc_khong_dat_kb11():
    ycd, hl = _kho_phu_du(10)
    hong = "/video/files/demo-3.mp4"
    kq = _kiem(ycd, hl, video_phat_duoc=lambda url: url != hong)
    assert kq["dat"] is False and kq["thieu"]


def test_link_ngoai_khong_bi_mo_thu_khi_kiem_do_phu_kb11():
    """US: hệ thống KHÔNG mở thử đường dẫn ngoài — chỉ video nội bộ được hỏi `video_phat_duoc`."""
    ycd, hl = _kho_phu_du(10)
    da_hoi: list[str] = []

    def hoi(url):
        da_hoi.append(url)
        return True

    _kiem(ycd, hl, video_phat_duoc=hoi)
    assert da_hoi and all(u.startswith("/video/files/") for u in da_hoi)

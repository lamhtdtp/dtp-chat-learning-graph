"""Soát tệp trước khi nạp — chốt chặn quan trọng nhất của luồng nạp sách.

Số trang lấy từ TÊN TỆP nên đoán sai là ghi đè trang thật và mọi dẫn nguồn
“[tr.9]” trỏ sai bài, không ai phát hiện cho tới khi học sinh đọc phải.
"""
import pytest

from app.ingestion import nap_sach


@pytest.mark.parametrize("ten,mong", [
    ("12.png", 12),                       # tên toàn số
    ("5.png", 5),
    ("045.png", 45),                      # có số 0 dẫn đầu
    ("trang-045.png", 45),
    ("Toan6_tap1_trang_132.jpg", 132),
    ("Scan (2).png", None),               # bản sao của Windows, KHÔNG phải trang 2
    ("p1.png", None),                     # một chữ số lẫn trong tên -> không chắc
    ("IMG_20250812_094512.jpg", None),    # có số nhưng vượt 999
    ("bia-sau.png", None),
    ("", None),
])
def test_so_trang_chi_nhan_khi_chac(ten, mong):
    assert nap_sach.so_trang(ten) == mong


def test_chon_trang_thu_bo_bia_va_phu_luc():
    """Phải rải trong PHẦN RUỘT sách.

    Rải đều trên cả tập nghe hợp lý nhưng đo trên sách thật (Toán 6 tập 1,
    151 trang) ra trang 1, 76, 151 — tức BÌA SÁCH và BẢNG SỐ NGUYÊN TỐ phụ lục.
    Hai trang đó OCR đúng hay sai đều không nói gì về việc đọc nổi công thức
    trong bài học.
    """
    t = nap_sach.chon_trang_thu(list(range(1, 152)), 3)
    assert t == [19, 76, 133]
    assert min(t) > 1 and max(t) < 151
    assert nap_sach.chon_trang_thu([7], 3) == [7]
    assert nap_sach.chon_trang_thu([], 3) == []
    assert len(nap_sach.chon_trang_thu([1, 2], 3)) == 2      # sách quá mỏng -> lấy hết


def test_co_cong_thuc_la_chi_so_chinh_cho_sach_toan():
    """OCR sách Toán vỡ ở CÔNG THỨC, không vỡ ở chữ."""
    assert nap_sach.co_cong_thuc("Tính $2^{3} \\cdot 5$") is True
    assert nap_sach.co_cong_thuc("24 ⋮ 6 nên 24 là bội của 6") is True
    assert nap_sach.co_cong_thuc("Số nguyên tố là số tự nhiên lớn hơn 1") is False


def test_soat_bao_trang_khuyet_o_giua_khong_bao_thieu_o_duoi(tmp_path, monkeypatch):
    monkeypatch.setattr(nap_sach, "DATA_ROOT", tmp_path)
    d = nap_sach.thu_muc("toan", "lop_6", 1, tao=True)
    for n in (1, 2, 3, 6, 7):
        (d / f"{n}.png").write_bytes(b"x")

    r = nap_sach.soat("toan", "lop_6", 1)
    assert r["trang"] == [1, 2, 3, 6, 7]
    assert r["thieu"] == [4, 5]        # hổng giữa = gần như chắc chắn bỏ sót
    assert r["cho_gan"] == []


def test_luu_tep_khong_tu_dat_so_cho_ten_la(tmp_path, monkeypatch):
    monkeypatch.setattr(nap_sach, "DATA_ROOT", tmp_path)
    r1 = nap_sach.luu_tep("toan", "lop_6", 1, "trang-045.png", b"anh")
    assert r1["so"] == 45 and r1["ghi_de"] is False
    r2 = nap_sach.luu_tep("toan", "lop_6", 1, "Scan (2).png", b"anh")
    assert r2["so"] is None and r2["cho_gan"] == "Scan (2).png"

    d = nap_sach.thu_muc("toan", "lop_6", 1)
    assert (d / "45.png").is_file()
    assert not (d / "2.png").exists()          # KHÔNG ghi đè trang 2
    assert (d / nap_sach.CHO_GAN / "Scan (2).png").is_file()

    r3 = nap_sach.luu_tep("toan", "lop_6", 1, "045.png", b"anh moi")
    assert r3["ghi_de"] is True                 # nạp lại phải nói rõ
    assert (d / "45.png").read_bytes() == b"anh moi"


def test_gan_so_trang_chuyen_tep_cho_thanh_trang_that(tmp_path, monkeypatch):
    monkeypatch.setattr(nap_sach, "DATA_ROOT", tmp_path)
    nap_sach.luu_tep("toan", "lop_6", 1, "Scan (2).png", b"anh")
    nap_sach.gan_so_trang("toan", "lop_6", 1, "Scan (2).png", 88)

    r = nap_sach.soat("toan", "lop_6", 1)
    assert r["trang"] == [88] and r["cho_gan"] == []
    with pytest.raises(FileNotFoundError):
        nap_sach.gan_so_trang("toan", "lop_6", 1, "Scan (2).png", 89)


def test_gan_so_trang_chan_so_vo_ly(tmp_path, monkeypatch):
    monkeypatch.setattr(nap_sach, "DATA_ROOT", tmp_path)
    nap_sach.luu_tep("toan", "lop_6", 1, "bia.png", b"anh")
    with pytest.raises(ValueError):
        nap_sach.gan_so_trang("toan", "lop_6", 1, "bia.png", 0)


def test_bo_tep_cho(tmp_path, monkeypatch):
    monkeypatch.setattr(nap_sach, "DATA_ROOT", tmp_path)
    nap_sach.luu_tep("toan", "lop_6", 1, "bia-sau.png", b"anh")
    nap_sach.bo_tep_cho("toan", "lop_6", 1, "bia-sau.png")
    assert nap_sach.soat("toan", "lop_6", 1)["cho_gan"] == []
    nap_sach.bo_tep_cho("toan", "lop_6", 1, "khong-co.png")     # không nổ


async def test_doc_thu_bao_co_bai_va_it_chu(tmp_path, monkeypatch, mocker):
    """`co_bai` là chỉ số đáng tin nhất: trang không nhận được “Bài mấy” thì đoạn
    tri thức mất ngữ cảnh, sau này AI soạn bài dẫn nguồn chung chung."""
    monkeypatch.setattr(nap_sach, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(nap_sach, "CACHE_ROOT", tmp_path / "cache")
    d = nap_sach.thu_muc("toan", "lop_6", 1, tao=True)
    for n in (10, 11, 12):
        (d / f"{n}.png").write_bytes(b"x")

    noi = {10: "# Bài 9. Ước và bội\nNếu a chia hết cho b thì a là bội của b." * 3,
           11: "vài chữ",
           12: "# Chương 2. Số nguyên\nnội dung dài " * 20}
    mocker.patch("app.ingestion.nap_sach.load_or_ocr_page",
                 mocker.AsyncMock(side_effect=lambda anh, *a, **k: noi[int(anh.stem)]))

    kq = await nap_sach.doc_thu("toan", "lop_6", 1, [10, 11, 12])
    assert [x["so"] for x in kq] == [10, 11, 12]
    assert kq[0]["co_bai"] is True and kq[0]["it_chu"] is False
    assert kq[1]["co_bai"] is False and kq[1]["it_chu"] is True
    assert kq[2]["co_chuong"] is True


async def test_doc_thu_mot_trang_loi_khong_lam_chet_ca_lo(tmp_path, monkeypatch, mocker):
    monkeypatch.setattr(nap_sach, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(nap_sach, "CACHE_ROOT", tmp_path / "cache")
    d = nap_sach.thu_muc("toan", "lop_6", 1, tao=True)
    for n in (1, 2):
        (d / f"{n}.png").write_bytes(b"x")

    async def ocr(anh, *a, **k):
        if int(anh.stem) == 1:
            raise RuntimeError("AI quá tải")
        return "# Bài 1. Tập hợp\n" + "x" * 200
    mocker.patch("app.ingestion.nap_sach.load_or_ocr_page", ocr)

    kq = await nap_sach.doc_thu("toan", "lop_6", 1, [1, 2, 99])
    assert kq[0]["loi"] == "AI quá tải"
    assert kq[1]["co_bai"] is True
    assert "không có ảnh" in kq[2]["loi"]        # trang không tồn tại -> báo rõ

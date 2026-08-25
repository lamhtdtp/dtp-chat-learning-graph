"""Job nạp sách: tiến độ theo trang, tạm dừng được, nạp tiếp không đọc lại."""
import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import BookJob
from app.ingestion import nap_sach, nap_sach_job


@pytest.fixture
def sach(tmp_path, monkeypatch):
    """Một tập 5 trang giả + cache trỏ vào tmp."""
    monkeypatch.setattr(nap_sach, "DATA_ROOT", tmp_path / "books")
    monkeypatch.setattr(nap_sach, "CACHE_ROOT", tmp_path / "cache")
    d = nap_sach.thu_muc("toan", "lop_6", 1, tao=True)
    for n in range(1, 6):
        (d / f"{n}.png").write_bytes(b"x")
    return d


def _md(n: int) -> str:
    # Trang 3 gần trắng -> phải bị gắn cờ it_chu; các trang khác có "Bài".
    return "trang hình" if n == 3 else f"# Bài {n}. Tiêu đề\n" + ("nội dung " * 40)


@pytest.fixture
def ocr(mocker):
    return mocker.patch("app.ingestion.tasks.load_or_ocr_page",
                        mocker.AsyncMock(side_effect=lambda anh, cache, **k: _md(int(anh.stem))))


async def _job(session, **kw) -> BookJob:
    j = BookJob(mon="toan", khoi="lop_6", tap=1, sach="ma_sach_test",
                trang_ds_json=json.dumps(kw.pop("trang", [1, 2, 3, 4, 5])), **kw)
    session.add(j)
    await session.flush()
    return j


def _factory(session):
    """session_factory giả trả về ĐÚNG session của test (để rollback dọn sạch)."""
    class Gia:
        def __call__(self):
            return self
        async def __aenter__(self):
            return session
        async def __aexit__(self, *a):
            return False
    return Gia()


async def test_chay_ghi_tien_do_theo_tung_trang(db_session, sach, ocr, mocker):
    up = mocker.patch("app.ingestion.nap_sach_job.upsert_chunks",
                      mocker.AsyncMock(return_value=17))
    # Ghi cache như OCR thật để bước soát đọc lại được.
    c = nap_sach.cache_dir("toan", 1); c.mkdir(parents=True, exist_ok=True)
    for n in range(1, 6):
        (c / f"{n}.md").write_text(_md(n), encoding="utf-8")

    j = await _job(db_session)
    await nap_sach_job.chay(j.id, session_factory=_factory(db_session))

    assert j.trang_thai == "xong" and j.buoc == "ghi_kho"
    assert json.loads(j.trang_xong_json) == [1, 2, 3, 4, 5]
    assert j.trang_dang is None and j.so_doan == 17
    assert up.await_count == 1

    # Trang 3 gần trắng -> cờ `it_chu`. KHÔNG phải `chua_gan_bai`:
    # `gan_chuong_bai_theo_trang` forward-fill nên trang không có heading vẫn kế
    # thừa "Bài" của trang trước — `chua_gan_bai` chỉ xảy ra ở phần đầu sách
    # (bìa, mục lục) trước heading "Bài" đầu tiên.
    soat = {x["so"]: x["ly_do"] for x in json.loads(j.trang_soat_json)}
    assert soat == {3: "it_chu"}
    assert j.so_trang_co_bai == 5


async def test_tam_dung_giua_duong_giu_nguyen_trang_da_doc(db_session, sach, ocr, mocker):
    """Bấm Tạm dừng: dừng êm sau trang đang đọc, KHÔNG mất trang đã xong."""
    mocker.patch("app.ingestion.nap_sach_job.upsert_chunks", mocker.AsyncMock(return_value=0))
    j = await _job(db_session)
    await db_session.commit()

    that = nap_sach_job._ghi

    async def ghi_roi_dung(session, job, **truong):
        await that(session, job, **truong)
        # Sau trang thứ 2, mô phỏng người soạn bấm Tạm dừng ở tiến trình khác.
        if len(json.loads(job.trang_xong_json or "[]")) == 2 and job.trang_thai == "dang":
            job.trang_thai = "tam_dung"
            await session.commit()
    mocker.patch.object(nap_sach_job, "_ghi", ghi_roi_dung)

    await nap_sach_job.chay(j.id, session_factory=_factory(db_session))
    assert j.trang_thai == "tam_dung"
    assert json.loads(j.trang_xong_json) == [1, 2]     # 2 trang đã đọc còn nguyên
    assert j.trang_dang is None


async def test_nap_tiep_khong_doc_lai_trang_da_xong(db_session, sach, ocr, mocker):
    """Cache OCR đã có nên nạp tiếp chỉ tốn từ trang đang dở."""
    mocker.patch("app.ingestion.nap_sach_job.upsert_chunks", mocker.AsyncMock(return_value=3))
    c = nap_sach.cache_dir("toan", 1); c.mkdir(parents=True, exist_ok=True)
    for n in range(1, 6):
        (c / f"{n}.md").write_text(_md(n), encoding="utf-8")

    j = await _job(db_session, trang_xong_json=json.dumps([1, 2, 3]), trang_thai="tam_dung")
    await nap_sach_job.chay(j.id, session_factory=_factory(db_session))

    assert j.trang_thai == "xong"
    assert json.loads(j.trang_xong_json) == [1, 2, 3, 4, 5]
    # chỉ gọi OCR cho 2 trang còn lại, không đọc lại 3 trang cũ
    assert sorted(int(k.args[0].stem) for k in ocr.await_args_list) == [4, 5]


async def test_mot_trang_loi_khong_lam_chet_ca_tap(db_session, sach, mocker):
    mocker.patch("app.ingestion.nap_sach_job.upsert_chunks", mocker.AsyncMock(return_value=9))

    async def ocr_loi(anh, cache, **k):
        n = int(anh.stem)
        if n == 3:
            raise RuntimeError("AI quá tải")
        return _md(n)
    mocker.patch("app.ingestion.tasks.load_or_ocr_page", ocr_loi)
    c = nap_sach.cache_dir("toan", 1); c.mkdir(parents=True, exist_ok=True)
    for n in (1, 2, 4, 5):
        (c / f"{n}.md").write_text(_md(n), encoding="utf-8")

    j = await _job(db_session)
    await nap_sach_job.chay(j.id, session_factory=_factory(db_session))

    assert j.trang_thai == "xong"                       # vẫn xong
    assert json.loads(j.trang_xong_json) == [1, 2, 4, 5]
    assert json.loads(j.trang_loi_json) == [{"so": 3, "ly_do": "AI quá tải"}]
    # trang lỗi phải hiện trong danh sách soát để người soạn đọc lại
    assert {"so": 3, "ly_do": "loi_doc", "chu": 0} in json.loads(j.trang_soat_json)


async def test_loi_ngoai_du_kien_ghi_vao_job_chu_khong_im_lang(db_session, sach, ocr, mocker):
    mocker.patch("app.ingestion.nap_sach_job.upsert_chunks",
                 mocker.AsyncMock(side_effect=RuntimeError("Qdrant sập")))
    c = nap_sach.cache_dir("toan", 1); c.mkdir(parents=True, exist_ok=True)
    for n in range(1, 6):
        (c / f"{n}.md").write_text(_md(n), encoding="utf-8")

    j = await _job(db_session)
    await nap_sach_job.chay(j.id, session_factory=_factory(db_session))
    assert j.trang_thai == "loi" and "Qdrant sập" in (j.loi or "")


async def test_job_khong_ton_tai_tra_none(db_session):
    assert await nap_sach_job.chay(10**9, session_factory=_factory(db_session)) is None


async def test_nap_le_mot_dai_trang_bao_thieu_ngu_canh_chu_khong_bao_sai_OCR(
        db_session, sach, ocr, mocker):
    """Nạp lẻ trang 3–5: forward-fill thiếu ngữ cảnh trang 1–2 nên trang đầu dải
    không có "Bài". Đó là hệ quả của nạp lẻ, KHÔNG phải OCR sai — cờ phải nói
    đúng nguyên nhân, không thì người soạn đi soát trang hoàn toàn bình thường.
    """
    mocker.patch("app.ingestion.nap_sach_job.upsert_chunks", mocker.AsyncMock(return_value=4))
    c = nap_sach.cache_dir("toan", 1); c.mkdir(parents=True, exist_ok=True)
    # Trang 3 gần trắng và KHÔNG có heading -> không kế thừa được gì
    for n in (3, 4, 5):
        (c / f"{n}.md").write_text("trang hình" if n == 3 else _md(n), encoding="utf-8")

    j = await _job(db_session, trang=[3, 4, 5])
    await nap_sach_job.chay(j.id, session_factory=_factory(db_session))

    ly_do = {x["so"]: x["ly_do"] for x in json.loads(j.trang_soat_json)}
    assert ly_do[3] == "thieu_ngu_canh"
    assert "chua_gan_bai" not in ly_do.values()


async def test_nap_ca_tap_thi_trang_dau_bao_chua_gan_bai(db_session, sach, ocr, mocker):
    """Nạp từ trang 1 mà vẫn không có "Bài" -> đúng là chưa gán được, cờ khác."""
    mocker.patch("app.ingestion.nap_sach_job.upsert_chunks", mocker.AsyncMock(return_value=4))
    c = nap_sach.cache_dir("toan", 1); c.mkdir(parents=True, exist_ok=True)
    (c / "1.md").write_text("BÌA SÁCH - không có heading nào " * 8, encoding="utf-8")
    for n in range(2, 6):
        (c / f"{n}.md").write_text(_md(n), encoding="utf-8")

    j = await _job(db_session, trang=[1, 2, 3, 4, 5])
    await nap_sach_job.chay(j.id, session_factory=_factory(db_session))

    ly_do = {x["so"]: x["ly_do"] for x in json.loads(j.trang_soat_json)}
    assert ly_do[1] == "chua_gan_bai"

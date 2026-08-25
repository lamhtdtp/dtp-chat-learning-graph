"""Chạy một job NẠP SÁCH và ghi tiến độ theo TRANG vào `book_jobs` (REQ §2.4).

Tách khỏi `celery_app` để test được mà không cần Celery, và tách khỏi `nap_sach`
(vốn chỉ là việc đồng bộ trên hệ tệp) vì đây là phần có DB + việc chạy lâu.
"""
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import BookJob
from app.ingestion import nap_sach
from app.ingestion.chunking import chunk_page
from app.ingestion.page_structure import gan_chuong_bai_theo_trang
from app.ingestion.qdrant_store import upsert_chunks
from app.ingestion.tasks import build_chunks_for_book

log = logging.getLogger(__name__)


class DaDung(Exception):
    """Người soạn bấm Tạm dừng — dừng êm, giữ nguyên các trang đã đọc."""


async def _ghi(session: AsyncSession, job: BookJob, **truong) -> None:
    for k, v in truong.items():
        setattr(job, k, v)
    await session.commit()


async def chay(job_id: int, session_factory=None) -> BookJob | None:
    """Đọc → cắt đoạn → ghi kho cho một job. Commit sau MỖI trang.

    Commit từng trang chứ không commit một lần ở cuối: cả tập mất 20–30 phút,
    nếu chỉ commit ở cuối thì UI đứng ở 0/149 suốt, và worker chết giữa đường là
    mất sạch dấu vết (cache OCR còn nhưng job không biết đã tới đâu).
    """
    engine = None
    if session_factory is None:
        # Engine RIÊNG: Celery bọc hàm này bằng asyncio.run -> mỗi task một event
        # loop mới, pool asyncpg của engine dùng chung sẽ lỗi 'different loop'.
        engine = create_async_engine(settings.database_url, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            job = await session.scalar(select(BookJob).where(BookJob.id == job_id))
            if job is None:
                log.warning("Không có job nạp sách id=%s", job_id)
                return None
            try:
                await _chay_job(session, job)
            except DaDung:
                await _ghi(session, job, trang_thai="tam_dung", trang_dang=None)
            except Exception as e:                  # noqa: BLE001 - ghi lỗi vào job
                log.exception("Job nạp sách %s lỗi", job_id)
                await _ghi(session, job, trang_thai="loi", trang_dang=None, loi=str(e)[:500])
            return job
    finally:
        if engine is not None:
            await engine.dispose()


async def _chay_job(session: AsyncSession, job: BookJob) -> None:
    trang = json.loads(job.trang_ds_json or "[]")
    xong: list[int] = json.loads(job.trang_xong_json or "[]")
    loi: list[dict] = json.loads(job.trang_loi_json or "[]")
    # Nạp tiếp: bỏ những trang đã đọc ở lần trước. Cache OCR đã có nên trang cũ
    # gần như miễn phí, nhưng vẫn không nên gọi lại API cho chúng.
    con_lai = [n for n in trang if n not in set(xong)]
    await _ghi(session, job, trang_thai="dang", buoc="doc", loi=None)

    async def on_page(so: int, _md: str) -> None:
        xong.append(so)
        await _ghi(session, job, trang_xong_json=json.dumps(xong), trang_dang=so)
        # Đọc lại trạng thái từ DB: người soạn bấm Tạm dừng ở tiến trình khác.
        await session.refresh(job, ["trang_thai"])
        if job.trang_thai == "tam_dung":
            raise DaDung

    async def on_loi(so: int, e: Exception) -> None:
        loi.append({"so": so, "ly_do": str(e)[:160]})
        await _ghi(session, job, trang_loi_json=json.dumps(loi, ensure_ascii=False))

    chunks = await build_chunks_for_book(
        mon=job.mon, khoi=job.khoi, sach=job.sach, tap=job.tap,
        book_dir=nap_sach.thu_muc(job.mon, job.khoi, job.tap),
        cache_dir=nap_sach.cache_dir(job.mon, job.tap),
        pages=con_lai, on_page=on_page, on_loi=on_loi,
    )

    # Cắt đoạn xong -> soát chất lượng. Chỉ giữ TRANG ĐÁNG NGỜ: bắt người soạn
    # lật 149 trang thì không ai lật, còn 11 trang thì có người xem.
    await _ghi(session, job, buoc="cat_doan", trang_dang=None)
    # Nạp MỘT PHẦN thì forward-fill chương/bài thiếu ngữ cảnh các trang phía
    # trước, nên mấy trang đầu dải gần như luôn không có "Bài". Đó là hệ quả của
    # việc nạp lẻ, không phải OCR sai — phải nói đúng nguyên nhân, không thì
    # người soạn đi soát 2 trang hoàn toàn bình thường.
    tat_ca = sorted(int(f.stem) for f in nap_sach.thu_muc(job.mon, job.khoi, job.tap)
                    .glob("*.png") if f.stem.isdigit())
    mot_phan = bool(tat_ca) and min(xong or [0]) > min(tat_ca)
    soat, co_bai = await _soat_trang(job, xong, mot_phan=mot_phan)
    soat += [{"so": x["so"], "ly_do": "loi_doc", "chu": 0} for x in loi]
    soat.sort(key=lambda x: x["so"])

    await _ghi(session, job, buoc="ghi_kho",
               trang_soat_json=json.dumps(soat, ensure_ascii=False),
               so_trang_co_bai=co_bai)
    so_doan = await upsert_chunks(chunks) if chunks else 0
    await _ghi(session, job, trang_thai="xong", buoc="ghi_kho",
               so_doan=so_doan, trang_dang=None)


async def _soat_trang(job: BookJob, trang: list[int],
                      mot_phan: bool = False) -> tuple[list[dict], int]:
    """Trang nào đáng ngờ, và bao nhiêu trang gán được chương/bài.

    Đọc lại từ cache OCR (miễn phí) thay vì giữ toàn bộ markdown trong bộ nhớ —
    151 trang markdown là hàng megabyte không cần thiết.
    """
    c = nap_sach.cache_dir(job.mon, job.tap)
    cap = []
    for n in sorted(trang):
        f = c / f"{n}.md"
        cap.append((n, f.read_text(encoding="utf-8") if f.is_file() else ""))

    ct = {s.page_no: s for s in gan_chuong_bai_theo_trang(cap)}
    ra, co_bai = [], 0
    for n, md in cap:
        s = ct.get(n)
        if s is not None and s.bai_so is not None:
            co_bai += 1
        else:
            ra.append({"so": n, "chu": len(md.strip()),
                       "ly_do": "thieu_ngu_canh" if mot_phan else "chua_gan_bai"})
            continue
        if len(md.strip()) < nap_sach.IT_CHU:
            ra.append({"so": n, "ly_do": "it_chu", "chu": len(md.strip())})
    return ra, co_bai


def dem_doan(job: BookJob) -> int:
    """Số đoạn ước tính từ cache — dùng khi cần đếm lại mà không ghi Qdrant."""
    c = nap_sach.cache_dir(job.mon, job.tap)
    cap = [(n, (c / f"{n}.md").read_text(encoding="utf-8"))
           for n in json.loads(job.trang_xong_json or "[]") if (c / f"{n}.md").is_file()]
    ct = {s.page_no: s for s in gan_chuong_bai_theo_trang(cap)}
    return sum(len(chunk_page(md, ct[n], mon=job.mon, khoi=job.khoi,
                              sach=job.sach, tap=job.tap)) for n, md in cap)

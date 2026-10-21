"""Nạp bộ học liệu DEMO vào kho (US-27) và kiểm độ phủ của nó.

    python -m app.seed_hoc_lieu                      # nạp app/seed_data/hoc_lieu_demo.json
    python -m app.seed_hoc_lieu --kiem-do-phu --ar-ids AR26-TO06-CK1-001,AR26-TO06-CK1-002,...

* Nạp lại được: mã đã có (kể cả đã xoá) thì BỎ QUA, không ghi đè bản người biên soạn đã sửa.
* CẤM bịa đường dẫn: file demo chỉ chứa video AI nội bộ CÓ THẬT (`video_jobs` DONE, tệp có
  trong kho video) và nguồn có thật. Không đủ để đạt ngưỡng KB 11 thì `--kiem-do-phu` nói rõ
  còn thiếu gì để chủ dự án bổ sung nội dung — không lấp bằng link giả.
* `--kiem-do-phu` cần `TESTBANK_*` để đổi `ar_id` sang nguyên văn YCCĐ (cùng cách khối Đề xuất làm).

`kiem_do_phu` là hàm thuần (test trên dữ liệu dựng sẵn, không đọc file demo).
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HocLieu
from app.lessons import de_xuat as de_xuat_svc
from app.lessons.ycd_key import chuan_hoa
from app.video import storage

log = logging.getLogger(__name__)

DEMO_JSON = Path(__file__).parent / "seed_data" / "hoc_lieu_demo.json"
_SACH = ("SGK", "SBT", "BTTC")
#: Ngưỡng KB 11.
_NUM_YCD_MIN, _NUM_YCD_MAX = 10, 12
_VIDEO_TOI_THIEU = 8
_CUNG_CO_TOI_THIEU = 3
_PHUONG_AN_TOI_THIEU = 2


def _video_noi_bo_phat_duoc(url: str) -> bool:
    return storage.resolve_url(url) is not None


def kiem_do_phu(ycd_demo: list[str], hoc_lieu: list[dict], *,
                video_phat_duoc: Callable[[str], bool] | None = None) -> dict:
    """Độ phủ của kho theo các YCCĐ của đề demo (US-27 KB 11).

    `ycd_demo`: nguyên văn YCCĐ của đề demo. `hoc_lieu`: dict `{ma, loai, muc_dich, ycd, qid,
    option_key, url}` (`muc_dich` = "on_lai" | "cung_co"). `video_phat_duoc(url)`: chỉ được hỏi cho
    video NỘI BỘ (`/video/files/...`) — link ngoài không bao giờ bị mở thử.

    Đạt khi: đề demo có 10-12 YCCĐ; mỗi YCCĐ có >= 1 học liệu Ôn lại loại SGK/SBT/BTTC; >= 8
    YCCĐ có >= 1 VIDEO Ôn lại; >= 3 YCCĐ có học liệu Củng cố; >= 2 CÂU có học liệu gắn theo một
    phương án; mọi video nội bộ phát được.

    Hai ngưỡng đầu chỉ tính học liệu gắn theo YCCĐ (không qid): học liệu gắn theo câu / phương
    án chỉ hiện khi em sai đúng câu đó nên không bảo đảm YCCĐ nào cũng có gì để xem.
    Trả `{"dat": bool, "thieu": [mô tả từng chỗ thiếu]}`."""
    video_phat_duoc = video_phat_duoc or _video_noi_bo_phat_duoc
    khoa_demo = {chuan_hoa(y): y for y in ycd_demo}
    thieu: list[str] = []
    if not _NUM_YCD_MIN <= len(khoa_demo) <= _NUM_YCD_MAX:
        thieu.append(f"Đề demo cần {_NUM_YCD_MIN}–{_NUM_YCD_MAX} YCCĐ (đang có {len(khoa_demo)})")

    cua = [h for h in hoc_lieu if chuan_hoa(h.get("ycd") or "") in khoa_demo]
    muc_ycd = [h for h in cua if not h.get("qid")]
    co_sach = {chuan_hoa(h["ycd"]) for h in muc_ycd
               if h["muc_dich"] == "on_lai" and h["loai"] in _SACH}
    for khoa, ycd in khoa_demo.items():
        if khoa not in co_sach:
            thieu.append(f"YCCĐ chưa có học liệu Ôn lại loại SGK/SBT/BTTC: {ycd}")

    co_video = {chuan_hoa(h["ycd"]) for h in muc_ycd if h["muc_dich"] == "on_lai" and h["loai"] == "VIDEO"}
    if len(co_video) < _VIDEO_TOI_THIEU:
        thieu.append(f"Mới {len(co_video)}/{_VIDEO_TOI_THIEU} YCCĐ có VIDEO Ôn lại")

    co_cung_co = {chuan_hoa(h["ycd"]) for h in cua if h["muc_dich"] == "cung_co"}
    if len(co_cung_co) < _CUNG_CO_TOI_THIEU:
        thieu.append(f"Mới {len(co_cung_co)}/{_CUNG_CO_TOI_THIEU} YCCĐ có học liệu Củng cố")

    cau_co_pa = {h["qid"] for h in cua if h.get("qid") and h.get("option_key") and h["muc_dich"] == "on_lai"}
    if len(cau_co_pa) < _PHUONG_AN_TOI_THIEU:
        thieu.append(f"Mới {len(cau_co_pa)}/{_PHUONG_AN_TOI_THIEU} câu có học liệu gắn theo một phương án sai")

    for h in hoc_lieu:
        url = h.get("url") or ""
        if h.get("loai") == "VIDEO" and de_xuat_svc.la_noi_bo(url) and not video_phat_duoc(url):
            thieu.append(f"Video nội bộ không phát được: {h['ma']} ({url})")
    return {"dat": not thieu, "thieu": thieu}


# ── Nạp ─────────────────────────────────────────────────────────────────────
def doc_file_demo(path: Path = DEMO_JSON) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


async def nap(session: AsyncSession, muc: list[dict]) -> tuple[int, int]:
    """Nạp từng học liệu; trả `(đã thêm, bỏ qua)`. Mã đã có thì bỏ qua. YCCĐ phải có trong danh mục —
    không có thì DỪNG, vì học liệu gắn vào YCCĐ không tồn tại sẽ không bao giờ hiện cho ai."""
    danh_muc = await de_xuat_svc.doc_danh_muc(session)
    them = bo_qua = 0
    for x in muc:
        ma = x["ma"].strip().upper()
        if await session.scalar(select(HocLieu.id).where(func.upper(HocLieu.ma) == ma)):
            bo_qua += 1
            continue
        m = danh_muc.tim(chuan_hoa(x["ycd"]))
        if m is None:
            raise SystemExit(f"{ma}: YCCĐ không có trong danh mục: {x['ycd']!r}")
        if x["loai"] == "VIDEO" and de_xuat_svc.la_noi_bo(x["url"]) and not _video_noi_bo_phat_duoc(x["url"]):
            raise SystemExit(f"{ma}: video nội bộ không có trong kho video: {x['url']}")
        session.add(HocLieu(ma=ma, loai=x["loai"], nhan=x["nhan"], url=x["url"], muc_dich=x["muc_dich"],
                            ycd_key=m.ycd_key, ycd_text=m.ycd_text, qid=x.get("qid"),
                            option_key=(x.get("option_key") or None)))
        them += 1
    await session.flush()
    return them, bo_qua


async def _ycd_cua_ar(ar_ids: list[str]) -> list[str]:
    from app.integrations.testbank.client import tao_client

    from app.integrations.testbank.client import TestbankChuaCauHinh, TestbankLoi

    try:
        _items, ar_ycd = await de_xuat_svc.doc_pool(tao_client())
    except TestbankChuaCauHinh as e:
        raise SystemExit(f"{e}. Đặt các biến TESTBANK_* (xem .env.example) rồi chạy lại.") from None
    except TestbankLoi as e:
        raise SystemExit(f"Không gọi được DTP Testbank để đổi mã YCCĐ: {e}") from None
    thieu = [a for a in ar_ids if a not in ar_ycd]
    if thieu:
        raise SystemExit(f"Testbank không có YCCĐ nào mang mã: {', '.join(thieu)}")
    return [ar_ycd[a] for a in ar_ids]


async def _main(args: argparse.Namespace) -> int:
    from app.db.session import async_session_factory

    async with async_session_factory() as session:
        if args.kiem_do_phu:
            ar_ids = [a.strip() for a in (args.ar_ids or "").split(",") if a.strip()]
            if not ar_ids:
                ar_ids = doc_file_demo().get("de_demo_ar_ids") or []
            ycd_demo = await _ycd_cua_ar(ar_ids)
            rows = (await session.scalars(select(HocLieu).where(HocLieu.xoa_luc.is_(None)))).all()
            kq = kiem_do_phu(ycd_demo, [{"ma": r.ma, "loai": r.loai, "muc_dich": r.muc_dich,
                                         "ycd": r.ycd_text, "qid": r.qid, "option_key": r.option_key,
                                         "url": r.url} for r in rows])
            print(f"Đề demo: {len(ycd_demo)} YCCĐ; kho có {len(rows)} học liệu.")
            print("ĐẠT" if kq["dat"] else "CHƯA ĐẠT — còn thiếu:")
            for t in kq["thieu"]:
                print(f"  - {t}")
            return 0 if kq["dat"] else 1
        them, bo_qua = await nap(session, doc_file_demo()["hoc_lieu"])
        await session.commit()
        print(f"Đã thêm {them} học liệu, bỏ qua {bo_qua} (mã đã có).")
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kiem-do-phu", action="store_true", help="in độ phủ thay vì nạp")
    ap.add_argument("--ar-ids", help="mã YCCĐ của đề demo, cách nhau bằng dấu phẩy (mặc định: trong file demo)")
    sys.exit(asyncio.run(_main(ap.parse_args())))


if __name__ == "__main__":
    main()

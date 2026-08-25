"""Báo cáo độ phủ 7 mục nội dung theo môn/khối.

    python -m app.bao_cao_phan [--mon "Toán"] [--khoi "Lớp 6"] [--thieu]

Nằm trong `app/` chứ không phải `scripts/`: infra/backend.Dockerfile chỉ COPY
`app` + `alembic`, nên script ở scripts/ KHÔNG có trong image và lệnh sẽ chết
trong container.

Dùng SAU mỗi lần chạy `app.seed_all_lessons` để biết còn thiếu mục nào ở bài nào
— hạn mức 50 request/ngày làm một lượt chạy không bao giờ xong cả bộ, nên phải
đo được phần còn lại chứ không chạy mù.

--thieu chỉ in các bài CHƯA đủ 7 mục (kèm trạng thái xuất bản: soạn đủ mà còn
'draft' thì học sinh vẫn không thấy gì).
"""
import argparse
import asyncio
import json

from sqlalchemy import select

from app.db.models import CurriculumTopic, Grade, Subject, TopicContent
from app.db.session import async_session_factory
from app.lessons import bo_cuc as bo_cuc_svc

# (id phần, nhãn ngắn để in bảng)
PHAN = [(p["id"], p["ten"]) for p in bo_cuc_svc.PHAN]


def _co(c: TopicContent | None, pid: str) -> bool:
    if c is None:
        return False
    if pid == "minh_hoa":
        return bool(json.loads(c.minh_hoa_json or "[]"))
    if pid == "vi_du":
        return bool(json.loads(c.vi_du_json or "[]"))
    return bool(bo_cuc_svc.noi_dung(c, pid).strip())


async def bao_cao(mon: str, khoi: str, chi_thieu: bool) -> None:
    async with async_session_factory() as s:
        subj = await s.scalar(select(Subject).filter_by(name=mon))
        gr = await s.scalar(select(Grade).filter_by(name=khoi))
        if subj is None or gr is None:
            print(f"✗ Không có {mon!r} / {khoi!r}")
            return
        topics = list(await s.scalars(
            select(CurriculumTopic).filter_by(subject_id=subj.id, grade_id=gr.id)
            .order_by(CurriculumTopic.order_index)))
        nd = {c.topic_id: c for c in await s.scalars(
            select(TopicContent).where(
                TopicContent.topic_id.in_([t.id for t in topics] or [0])))}

    dem = {pid: 0 for pid, _ in PHAN}
    xuat_ban = du = 0
    dong = []
    for t in topics:
        c = nd.get(t.id)
        co = [_co(c, pid) for pid, _ in PHAN]
        n = sum(co)
        du += n == len(PHAN)
        xuat_ban += bool(c and c.trang_thai == "published")
        for (pid, _), v in zip(PHAN, co):
            dem[pid] += v
        if chi_thieu and n == len(PHAN):
            continue
        dong.append((t, c, co, n))

    print(f"{mon} · {khoi} — {len(topics)} đơn vị · đủ 7 mục: {du} · đã xuất bản: {xuat_ban}\n")
    print("     " + " ".join(f"{i+1}" for i in range(len(PHAN))) + "  n/7  tt   đơn vị")
    for t, c, co, n in dong:
        o = " ".join("█" if v else "·" for v in co)
        tt = {"published": "XB", "review": "cd", "draft": "np"}.get(
            c.trang_thai if c else "", "--")
        print(f"  {t.id:>5} {o}  {n}/7  {tt}  {t.don_vi_kien_thuc[:44]}")

    print("\nSố bài CÓ từng mục:")
    for i, (pid, ten) in enumerate(PHAN, 1):
        v = dem[pid]
        print(f"  {i}. {ten:22} {v:>3}/{len(topics)}  {'█' * v}")
    thieu = [ten for pid, ten in PHAN if dem[pid] < len(topics)]
    if thieu:
        print("\nCòn thiếu ở một số bài: " + ", ".join(thieu))
        print("  → chữ:  python -m app.seed_all_lessons --phan")
        print("  → ảnh:  python -m app.seed_all_lessons --media")
    if du and xuat_ban < len(topics):
        print(f"\n⚠️  {len(topics) - xuat_ban} bài CHƯA xuất bản — học sinh không thấy. "
              "Xuất bản trong CMS, hoặc chạy lại kèm --publish.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Độ phủ 7 mục nội dung")
    ap.add_argument("--mon", default="Toán")
    ap.add_argument("--khoi", default="Lớp 6")
    ap.add_argument("--thieu", action="store_true", help="chỉ in bài chưa đủ 7 mục")
    a = ap.parse_args()
    asyncio.run(bao_cao(a.mon, a.khoi, a.thieu))


if __name__ == "__main__":
    main()

"""Nạp ma trận đặc tả (Toán 6) vào Postgres — điều kiện để /exam/generate chạy.
Thiếu bước này -> service.sinh_de raise BlueprintNotFound -> API trả 404.

    python -m app.exam.load_matrix_cli                 # nạp cả HK1 + HK2
    python -m app.exam.load_matrix_cli --hoc-ky hk1    # chỉ 1 học kỳ

File .docx đọc từ data/matrix/ (mount ./data vào container). load_matrix idempotent
(xoá blueprint cũ cùng môn/khối/kỳ rồi nạp lại) — chạy nhiều lần an toàn.
"""

import argparse
import asyncio
from pathlib import Path

from app.db.session import async_session_factory
from app.exam.matrix_loader import load_matrix

# (mon hiển thị, khối, học kỳ, đường dẫn) — Toán .docx, Tiếng Anh .md (parse_matrix
# tự chọn parser theo đuôi). File nào không có -> bỏ qua (in cảnh báo).
_MATRICES = [
    ("Toán", "Lớp 6", "hk1", Path("data/matrix/TOAN_6_HK1.docx")),
    ("Toán", "Lớp 6", "hk2", Path("data/matrix/TOAN_6_HK2.docx")),
    ("Tiếng Anh", "Lớp 6", "hk1", Path("data/matrix/ANH_6_HK1.md")),
    ("Tiếng Anh", "Lớp 6", "hk2", Path("data/matrix/ANH_6_HK2.md")),
]


async def _main(hoc_ky: str | None, mon: str | None) -> None:
    from sqlalchemy import func, select
    from app.db.models import BlueprintCell

    targets = [
        t for t in _MATRICES
        if (hoc_ky is None or t[2] == hoc_ky) and (mon is None or t[0] == mon)
    ]
    async with async_session_factory() as session:
        for mon_ten, khoi, hk, path in targets:
            if not path.exists():
                print(f"BỎ QUA {mon_ten} {hk}: không thấy {path} (copy vào data/matrix/ trên server)")
                continue
            bp = await load_matrix(session, path, mon=mon_ten, khoi=khoi, hoc_ky=hk)
            n = await session.scalar(
                select(func.count()).select_from(BlueprintCell).where(BlueprintCell.blueprint_id == bp.id)
            )
            print(f"Nạp {mon_ten} {hk}: blueprint id={bp.id}, {n} ô ma trận")
            # Cảnh báo NGAY trên terminal: đơn vị tự tạo mang tên lấy thô từ Word
            # nên hay trùng/sai chính tả với đơn vị đã có. Im lặng thì danh mục
            # phình thêm mà không ai biết.
            moi = getattr(bp, "don_vi_moi", [])
            if moi:
                print(f"  ⚠️  TỰ TẠO {len(moi)} đơn vị kiến thức chưa có trong danh mục "
                      f"— vào CMS › Ma trận đặc tả để rà lại tên:")
                for t in moi[:10]:
                    print(f"       · {t.mach_noi_dung} / {t.don_vi_kien_thuc}")
                if len(moi) > 10:
                    print(f"       … và {len(moi) - 10} đơn vị nữa")
        await session.commit()
    print("Đã nạp ma trận + commit.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Nạp ma trận (Toán .docx + Tiếng Anh .md) vào Postgres")
    ap.add_argument("--hoc-ky", choices=["hk1", "hk2"], default=None, help="bỏ trống = cả 2 kỳ")
    ap.add_argument("--mon", choices=["Toán", "Tiếng Anh"], default=None, help="bỏ trống = mọi môn")
    args = ap.parse_args()
    asyncio.run(_main(args.hoc_ky, args.mon))


if __name__ == "__main__":
    main()

"""Eval "khớp ma trận" — ngưỡng 100%. Phép kiểm bản chất là ĐẾM (deterministic)
nên đạt 100% tuyệt đối, không phải xác suất (xem testing-tdd-eval Phần D ghi
chú). Kiểm 2 điều trên ma trận thật đã nạp Postgres:
  1. build_blueprint từ tỉ lệ ma trận -> tổng số câu khớp chính xác tong_so_cau.
  2. một "đề" đếm theo mức độ khớp đúng chỉ tiêu blueprint.

    python -m evals.run_matrix_eval
"""

import asyncio
from pathlib import Path

from sqlalchemy import select

from app.db.models import Blueprint, BlueprintCell
from app.db.session import async_session_factory
from app.exam.blueprint import build_blueprint
from app.exam.check import CauHoi, DeThi, kiem_tra_ti_le
from app.exam.matrix_loader import load_matrix

HK1 = Path(__file__).resolve().parents[1] / "data" / "matrix" / "TOAN_6_HK1.docx"


async def _ti_le_theo_muc_do(session, blueprint_id: int) -> dict[str, float]:
    """Tổng tỉ lệ theo mức độ từ blueprint_cells đã nạp. Dedupe theo
    `nhom_ti_le` — mỗi nhóm tỉ lệ chỉ cộng 1 lần (nhiều cell cùng nhóm chia sẻ
    một mức tỉ lệ chung)."""
    cells = list(await session.scalars(
        select(BlueprintCell).where(BlueprintCell.blueprint_id == blueprint_id)))
    seen, totals = set(), {}
    for c in cells:
        if c.nhom_ti_le in seen:
            continue
        seen.add(c.nhom_ti_le)
        totals[c.muc_do] = totals.get(c.muc_do, 0.0) + c.ti_le
    return totals


async def _main() -> None:
    # Eval KHÔNG mutate DB thật: load trong session rồi rollback (dữ liệu vẫn
    # thấy được trong session nhờ flush của load_matrix, không cần commit).
    async with async_session_factory() as session:
        bp = await load_matrix(session, HK1, hoc_ky="hk1")
        ti_le = await _ti_le_theo_muc_do(session, bp.id)
        await session.rollback()

    checks = []
    for tong in [10, 20, 7, 33]:
        chi_tieu = build_blueprint(ti_le, tong_so_cau=tong)
        khop_tong = sum(chi_tieu.values()) == tong
        # dựng "đề" đúng chỉ tiêu rồi đếm lại -> phải khớp 100%
        de = DeThi(cau_hoi=[CauHoi(muc_do=md) for md, n in chi_tieu.items() for _ in range(n)])
        khop_dem = kiem_tra_ti_le(de, chi_tieu)
        checks.append((tong, chi_tieu, khop_tong and khop_dem))
        print(f"  tong={tong:>3} -> {chi_tieu}  tổng khớp={khop_tong} đếm khớp={khop_dem}")

    ok = all(c[2] for c in checks)
    print(f"\nKhớp ma trận: {sum(c[2] for c in checks)}/{len(checks)} — ngưỡng 100%")
    print("KẾT QUẢ:", "ĐẠT (100%)" if ok else "SAI — có ca không khớp")


if __name__ == "__main__":
    asyncio.run(_main())

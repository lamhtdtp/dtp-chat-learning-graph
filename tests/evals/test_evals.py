"""Eval chạy như test (job riêng, theo dõi hồi quy). Khớp ma trận là ĐẾM ->
ngưỡng cứng 100%. Retrieval là xác suất -> ngưỡng recall@5, skip nếu chưa có
dữ liệu/không API key."""

from pathlib import Path

import pytest

from app.config import settings

REPO_ROOT = Path(__file__).resolve().parents[2]
HK1 = REPO_ROOT / "data" / "matrix" / "TOAN_6_HK1.docx"


@pytest.mark.skipif(not HK1.exists(), reason="Cần ma trận thật")
async def test_khop_ma_tran_100_phan_tram(db_session):
    from app.exam.blueprint import build_blueprint
    from app.exam.check import CauHoi, DeThi, kiem_tra_ti_le
    from app.exam.matrix_loader import load_matrix
    from evals.run_matrix_eval import _ti_le_theo_muc_do

    bp = await load_matrix(db_session, HK1, hoc_ky="hk1")
    ti_le = await _ti_le_theo_muc_do(db_session, bp.id)

    assert sum(ti_le.values()) == 100.0  # tổng tỉ lệ ma trận = 100%
    for tong in [10, 20, 7, 33]:
        chi_tieu = build_blueprint(ti_le, tong_so_cau=tong)
        assert sum(chi_tieu.values()) == tong  # không mất câu do làm tròn
        de = DeThi(cau_hoi=[CauHoi(muc_do=m) for m, n in chi_tieu.items() for _ in range(n)])
        assert kiem_tra_ti_le(de, chi_tieu)  # đếm lại khớp 100%


@pytest.mark.skipif(not settings.ai_platform_api_key, reason="Cần API key để embed")
async def test_retrieval_recall_at_5_dat_nguong():
    from qdrant_client import AsyncQdrantClient

    from evals.run_retrieval_eval import NGUONG, danh_gia

    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        has_data = (
            await client.collection_exists(settings.qdrant_collection)
            and (await client.count(settings.qdrant_collection)).count > 0
        )
    except Exception:
        pytest.skip("Qdrant chưa chạy/không kết nối được")
    if not has_data:
        pytest.skip("Qdrant chưa có dữ liệu — chạy ingestion trước")

    kq = await danh_gia()
    assert kq["recall_at_k"] >= NGUONG, f"recall@5={kq['recall_at_k']:.3f} dưới ngưỡng {NGUONG}"

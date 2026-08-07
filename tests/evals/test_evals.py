"""Eval chạy như test (job riêng, theo dõi hồi quy). Retrieval là xác suất ->
ngưỡng recall@5, skip nếu chưa có dữ liệu/không API key. (Eval khớp ma trận đã
gỡ cùng tính năng sinh đề ở P5 — quiz P3 dùng ma trận nhưng không sinh đề đầy đủ.)"""

import pytest

from app.config import settings


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

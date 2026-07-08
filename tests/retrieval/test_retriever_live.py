"""Test retrieval THẬT trên Qdrant đã nạp dữ liệu. Skip nếu chưa có API key
hoặc collection rỗng (CI/máy chưa ingest) — không mock, để bắt hồi quy chất
lượng embedding/filter trên nội dung tiếng Việt thật."""

import pytest
from qdrant_client import AsyncQdrantClient

from app.config import settings
from app.retrieval import retriever


async def _collection_count() -> int:
    try:
        client = AsyncQdrantClient(url=settings.qdrant_url)
        if not await client.collection_exists(settings.qdrant_collection):
            return 0
        return (await client.count(settings.qdrant_collection)).count
    except Exception:
        return 0


needs_data = pytest.mark.skipif(
    not settings.ai_platform_api_key, reason="Cần AI_PLATFORM_API_KEY để embed query"
)


@needs_data
async def test_retrieve_that_tra_ve_chunk_lien_quan():
    if await _collection_count() == 0:
        pytest.skip("Qdrant chưa có dữ liệu — chạy `python -m app.ingestion.cli` trước")

    results = await retriever.retrieve(
        "cách viết một tập hợp", mon="toan", khoi="lop_6", top_k=3
    )

    assert results, "phải tìm được ít nhất 1 chunk liên quan"
    assert results == sorted(results, key=lambda r: r.score, reverse=True)  # sắp giảm dần
    assert all(r.page_no > 0 for r in results)


@needs_data
async def test_retrieve_filter_khoi_khac_tra_ve_rong():
    if await _collection_count() == 0:
        pytest.skip("Qdrant chưa có dữ liệu")

    # lọc khối không tồn tại -> không nhiễu chéo, trả rỗng
    results = await retriever.retrieve(
        "tập hợp", mon="toan", khoi="lop_99", top_k=3
    )
    assert results == []

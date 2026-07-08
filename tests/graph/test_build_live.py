"""Test graph THẬT với Redis Stack checkpointer + Qdrant + Gemile. Skip nếu
thiếu API key hoặc Redis Stack chưa chạy (cần RediSearch — xem docker-compose).
Khoá lại việc ghép graph + checkpointer Redis hoạt động thật, không chỉ mock."""

import pytest

from app.config import settings


async def _redis_ready() -> bool:
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url)
        modules = await client.execute_command("MODULE", "LIST")
        await client.aclose()
        return any(b"search" in bytes(m).lower() for row in modules for m in row if isinstance(m, (bytes, bytearray)))
    except Exception:
        return False


@pytest.mark.skipif(not settings.ai_platform_api_key, reason="Cần AI_PLATFORM_API_KEY")
async def test_graph_that_qua_redis_checkpointer():
    if not await _redis_ready():
        pytest.skip("Cần Redis Stack (RediSearch) tại REDIS_URL — docker compose up redis")

    from app.graph.build import build_graph_with_redis

    async with build_graph_with_redis() as app:
        out = await app.ainvoke(
            {"messages": [{"role": "user", "content": "Tập hợp là gì?"}], "role": "hoc_sinh"},
            config={"configurable": {"thread_id": "pytest-live"}},
        )

    assert out["intent"] == "hoi_dap"
    assert isinstance(out["answer"], str) and out["answer"].strip()

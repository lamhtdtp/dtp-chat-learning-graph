"""Luồng OFFLINE đồng bộ Itest (EPIC-10, US-21/US-22): đọc DB Itest read-only ->
mirror -> gợi ý ánh xạ taxonomy. Chạy nền qua Celery, KHÔNG chặn đường chat.

Lỗi kết nối Itest được đẩy lên để Celery retry — không để mirror nửa vời.
"""

from __future__ import annotations

from app.db.session import async_session_factory
from app.integrations.itest import mapping, sync
from app.integrations.itest.source import DbItestSource, ItestSource


async def run_sync(source: ItestSource | None = None) -> dict:
    """Đồng bộ mirror rồi gợi ý ánh xạ cho tag mới. Commit 1 lần cuối (idempotent
    nên retry an toàn). `source=None` -> DbItestSource từ ITEST_DATABASE_URL."""
    src = source or DbItestSource()
    async with async_session_factory() as session:
        sync_report = await sync.sync_questions(session, src)
        map_report = await mapping.map_unmapped_tags(session)
        await session.commit()
    return {
        "sync": sync_report.model_dump(),
        "map": map_report.model_dump(),
    }

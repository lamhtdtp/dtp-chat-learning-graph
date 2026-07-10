"""Đồng bộ ngân hàng Itest -> mirror `itest_questions` (EPIC-10, US-21).

Idempotent theo `itest_id` + `content_hash`: câu mới -> insert; nội dung đổi
(khác hash) -> update; không đổi -> bỏ qua. Nguồn (`ItestSource`) là READ-ONLY:
sync chỉ ĐỌC từ nguồn và GHI vào mirror Postgres, không bao giờ ghi ngược Itest.
Lỗi nguồn được đẩy lên để tầng gọi (Celery) retry — không để mirror nửa vời.
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ItestQuestion
from app.integrations.itest.source import ItestSource


class SyncReport(BaseModel):
    them_moi: int = 0
    cap_nhat: int = 0
    khong_doi: int = 0

    @property
    def tong(self) -> int:
        return self.them_moi + self.cap_nhat + self.khong_doi


async def sync_questions(session: AsyncSession, source: ItestSource) -> SyncReport:
    """Đọc câu hỏi từ `source` (read-only) và upsert vào mirror. Trả báo cáo
    số câu thêm/cập nhật/không đổi."""
    records = await source.fetch_questions()
    report = SyncReport()

    for rec in records:
        new_hash = rec.content_hash()
        existing = await session.scalar(
            select(ItestQuestion).where(ItestQuestion.itest_id == rec.itest_id)
        )
        if existing is None:
            session.add(
                ItestQuestion(
                    itest_id=rec.itest_id,
                    tag_goc=rec.tag_goc,
                    question_type=rec.question_type,
                    noi_dung=rec.noi_dung,
                    options_json=_dump_options(rec.options),
                    dap_an=rec.dap_an or None,
                    loi_giai=rec.loi_giai or None,
                    image_url=rec.image_url,
                    content_hash=new_hash,
                )
            )
            report.them_moi += 1
        elif existing.content_hash != new_hash:
            existing.tag_goc = rec.tag_goc
            existing.question_type = rec.question_type
            existing.noi_dung = rec.noi_dung
            existing.options_json = _dump_options(rec.options)
            existing.dap_an = rec.dap_an or None
            existing.loi_giai = rec.loi_giai or None
            existing.image_url = rec.image_url
            existing.content_hash = new_hash
            report.cap_nhat += 1
        else:
            report.khong_doi += 1

    await session.flush()
    return report


def _dump_options(options: list[str]) -> str | None:
    import json

    return json.dumps(options, ensure_ascii=False) if options else None

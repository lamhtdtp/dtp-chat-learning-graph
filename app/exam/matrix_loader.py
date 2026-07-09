"""Nạp ma trận .docx đã parse vào Postgres: subjects/grades/curriculum_topics/
blueprints/blueprint_cells. Idempotent theo (mon, khoi, hoc_ky) — chạy lại
không tạo trùng.

curriculum_topics là "xương sống" nối SGK (Qdrant) với ma trận: rút từ cột
(mach_noi_dung, don_vi_kien_thuc), dedupe, gán order_index theo thứ tự xuất
hiện. blueprint_cells.topic_id trỏ vào đây.
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Blueprint, BlueprintCell, CurriculumTopic, Grade, Subject
from app.ingestion.matrix_parser import parse_matrix_docx


async def _get_or_create(session: AsyncSession, model, defaults=None, **keys):
    obj = await session.scalar(select(model).filter_by(**keys))
    if obj is None:
        obj = model(**keys, **(defaults or {}))
        session.add(obj)
        await session.flush()
    return obj


async def load_matrix(
    session: AsyncSession,
    path: str | Path,
    *,
    mon: str = "Toán",
    khoi: str = "Lớp 6",
    hoc_ky: str,
) -> Blueprint:
    records = parse_matrix_docx(path)

    subject = await _get_or_create(session, Subject, name=mon)
    grade = await _get_or_create(session, Grade, name=khoi)

    # Xoá blueprint cũ cùng (mon, khoi, hoc_ky) để nạp lại sạch (idempotent).
    old = await session.scalar(
        select(Blueprint).filter_by(subject_id=subject.id, grade_id=grade.id, semester=hoc_ky)
    )
    if old is not None:
        for cell in await session.scalars(select(BlueprintCell).filter_by(blueprint_id=old.id)):
            await session.delete(cell)
        await session.flush()  # xoá cell TRƯỚC (model chưa khai cascade nên phải
        await session.delete(old)  # tự đảm bảo thứ tự, tránh vi phạm FK)
        await session.flush()

    blueprint = Blueprint(subject_id=subject.id, grade_id=grade.id, semester=hoc_ky)
    session.add(blueprint)
    await session.flush()

    # curriculum_topics dedupe theo (mach_noi_dung, don_vi_kien_thuc), gán
    # order_index theo thứ tự xuất hiện lần đầu.
    topic_cache: dict[tuple[str, str], CurriculumTopic] = {}
    for rec in records:
        key = (rec.mach_noi_dung, rec.don_vi_kien_thuc)
        topic = topic_cache.get(key)
        if topic is None:
            topic = await session.scalar(
                select(CurriculumTopic).filter_by(
                    subject_id=subject.id, grade_id=grade.id,
                    mach_noi_dung=rec.mach_noi_dung, don_vi_kien_thuc=rec.don_vi_kien_thuc,
                )
            )
            if topic is None:
                topic = CurriculumTopic(
                    subject_id=subject.id, grade_id=grade.id,
                    mach_noi_dung=rec.mach_noi_dung, don_vi_kien_thuc=rec.don_vi_kien_thuc,
                    order_index=len(topic_cache),
                )
                session.add(topic)
                await session.flush()
            topic_cache[key] = topic

        session.add(BlueprintCell(
            blueprint_id=blueprint.id,
            muc_do=rec.muc_do,
            nang_luc=rec.nang_luc_thanh_phan,
            yeu_cau_can_dat=rec.yeu_cau_can_dat,
            topic_id=topic.id,
            dang_thuc=rec.dang_thuc,
            ti_le=rec.ti_le,
            nhom_ti_le=rec.nhom_ti_le,
        ))

    await session.flush()
    return blueprint

"""Ánh xạ tag Itest (tên đề) -> taxonomy chương trình (EPIC-10, US-22).

LLM (qua app.llm.gateway, được trace) GỢI Ý ánh xạ; người duyệt xác nhận mới
dùng. Câu chưa map được đánh dấu 'chua_map' và đếm vào báo cáo — KHÔNG âm thầm
bỏ. Chỉ tag 'da_duyet' mới đủ điều kiện suggest (xem itest_suggest.py).
"""

from __future__ import annotations

import json

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CurriculumTopic, ItestQuestion, ItestTopicMap
from app.llm import gateway

_MUC_DO = {"de", "trung_binh", "kho"}


class MapReport(BaseModel):
    goi_y_moi: int = 0      # tag mới được LLM gợi ý (cho_duyet)
    chua_map: int = 0       # tag LLM không map được (đánh dấu, không bỏ)
    da_co: int = 0          # tag đã có bản ghi map từ trước


def _mapping_prompt(tag: str, vi_du: list[str], topics: list[CurriculumTopic]) -> list[dict]:
    ds_topic = "\n".join(f"- id={t.id}: {t.mach_noi_dung} / {t.don_vi_kien_thuc}" for t in topics)
    vd = "\n".join(f"  • {v}" for v in vi_du[:5])
    noi_dung = (
        "Bạn phân loại một ĐỀ trắc nghiệm Toán lớp 6 vào chương trình.\n"
        f"Tên đề (tag Itest): {tag!r}\n"
        f"Vài câu hỏi ví dụ trong đề:\n{vd}\n\n"
        f"Danh sách đơn vị kiến thức (topic) hợp lệ:\n{ds_topic}\n\n"
        "Chọn topic phù hợp NHẤT và mức độ chủ đạo của đề. Mức độ ∈ "
        '{"de","trung_binh","kho"}. Nếu KHÔNG thuộc chương trình nào, trả '
        '{"khong_map": true}. CHỈ trả JSON, không giải thích:\n'
        '{"topic_id": <int>, "muc_do": "<de|trung_binh|kho>"}'
    )
    return [{"role": "user", "content": noi_dung}]


def _parse_suggestion(raw: str, valid_topic_ids: set[int]) -> tuple[int, str] | None:
    """Đọc JSON đề xuất của LLM. Trả (topic_id, muc_do) hợp lệ, hoặc None nếu
    LLM báo không map / JSON hỏng / topic_id không hợp lệ."""
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if data.get("khong_map"):
        return None
    topic_id = data.get("topic_id")
    if topic_id not in valid_topic_ids:
        return None
    # LLM trả mã canonical ("de"/"trung_binh"/"kho" theo prompt); mức lạ -> mặc
    # định trung bình (vẫn map được, không loại câu vì lỗi diễn đạt mức độ).
    muc_do = str(data.get("muc_do", "")).strip().lower()
    if muc_do not in _MUC_DO:
        muc_do = "trung_binh"
    return int(topic_id), muc_do


async def suggest_mapping(
    tag: str, vi_du: list[str], topics: list[CurriculumTopic]
) -> tuple[int, str] | None:
    """Gọi LLM gợi ý ánh xạ 1 tag -> (topic_id, muc_do). None nếu không map được."""
    raw = await gateway.complete("itest_map", _mapping_prompt(tag, vi_du, topics), max_tokens=256)
    return _parse_suggestion(raw, {t.id for t in topics})


async def map_unmapped_tags(
    session: AsyncSession, *, mon: str = "Toán", khoi: str = "Lớp 6"
) -> MapReport:
    """Với mỗi tag trong mirror CHƯA có bản ghi map: gọi LLM gợi ý, lưu
    'cho_duyet'; không map được -> lưu 'chua_map' (đếm, không bỏ)."""
    from app.db.models import Grade, Subject

    subject = await session.scalar(select(Subject).filter_by(name=mon))
    grade = await session.scalar(select(Grade).filter_by(name=khoi))
    topics = list(
        await session.scalars(
            select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id)
        )
    ) if subject and grade else []

    tags = list(await session.scalars(select(ItestQuestion.tag_goc).distinct()))
    da_map = set(await session.scalars(select(ItestTopicMap.itest_tag)))
    report = MapReport()

    for tag in tags:
        if tag in da_map:
            report.da_co += 1
            continue
        vi_du = list(await session.scalars(
            select(ItestQuestion.noi_dung).where(ItestQuestion.tag_goc == tag).limit(5)
        ))
        suggestion = await suggest_mapping(tag, vi_du, topics)
        if suggestion is None:
            session.add(ItestTopicMap(itest_tag=tag, status="chua_map"))
            report.chua_map += 1
        else:
            topic_id, muc_do = suggestion
            session.add(ItestTopicMap(
                itest_tag=tag, topic_id=topic_id, muc_do=muc_do, status="cho_duyet"
            ))
            report.goi_y_moi += 1

    await session.flush()
    return report


async def approve_mapping(session: AsyncSession, map_id: int) -> ItestTopicMap:
    """Người duyệt xác nhận 1 ánh xạ -> 'da_duyet' (đủ điều kiện suggest)."""
    row = await session.get(ItestTopicMap, map_id)
    if row is None:
        raise ValueError(f"Không có ánh xạ id={map_id}")
    if row.topic_id is None:
        raise ValueError("Không thể duyệt ánh xạ chưa có topic (status 'chua_map')")
    row.status = "da_duyet"
    await session.flush()
    return row

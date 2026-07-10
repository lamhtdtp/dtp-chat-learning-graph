"""US-22 (DB): map_unmapped_tags gợi ý + đánh dấu chua_map; approve_mapping duyệt."""

import pytest
from sqlalchemy import select

from app.db.models import CurriculumTopic, Grade, ItestQuestion, ItestTopicMap, Subject
from app.integrations.itest import mapping


async def _seed_taxonomy(session):
    subject = await session.scalar(select(Subject).filter_by(name="Toán")) or Subject(name="Toán")
    grade = await session.scalar(select(Grade).filter_by(name="Lớp 6")) or Grade(name="Lớp 6")
    session.add_all([subject, grade])
    await session.flush()
    topic = CurriculumTopic(
        subject_id=subject.id, grade_id=grade.id,
        mach_noi_dung="Số tự nhiên", don_vi_kien_thuc="Số nguyên tố", order_index=1,
    )
    session.add(topic)
    await session.flush()
    return topic


async def test_map_unmapped_danh_dau_chua_map_khong_bo(db_session, mocker):
    topic = await _seed_taxonomy(db_session)
    db_session.add_all([
        ItestQuestion(itest_id="a1", tag_goc="Đề Số nguyên tố", question_type="MC",
                      noi_dung="7 là số nguyên tố?", content_hash="h1"),
        ItestQuestion(itest_id="b1", tag_goc="Đề Vật Lý", question_type="MC",
                      noi_dung="lạc đề", content_hash="h2"),
    ])
    await db_session.flush()

    # LLM map được ĐÚNG đề Toán mình seed, không map được đề Vật Lý.
    async def fake_suggest(tag, vi_du, topics):
        return (topic.id, "de") if tag == "Đề Số nguyên tố" else None
    mocker.patch.object(mapping, "suggest_mapping", side_effect=fake_suggest)

    report = await mapping.map_unmapped_tags(db_session)

    assert report.goi_y_moi >= 1
    assert report.chua_map >= 1  # đề lạc không bị bỏ im lặng (đếm, không loại)
    # Kiểm đúng 2 tag đã seed (bền vững kể cả khi mirror đã có dữ liệu thật).
    rows = {r.itest_tag: r for r in await db_session.scalars(
        select(ItestTopicMap).where(ItestTopicMap.itest_tag.in_(["Đề Số nguyên tố", "Đề Vật Lý"]))
    )}
    assert rows["Đề Số nguyên tố"].status == "cho_duyet"
    assert rows["Đề Vật Lý"].status == "chua_map"
    assert rows["Đề Vật Lý"].topic_id is None


async def test_approve_mapping_chuyen_da_duyet(db_session):
    topic = await _seed_taxonomy(db_session)
    m = ItestTopicMap(itest_tag="Đề A", topic_id=topic.id, muc_do="de", status="cho_duyet")
    db_session.add(m)
    await db_session.flush()

    await mapping.approve_mapping(db_session, m.id)
    assert m.status == "da_duyet"


async def test_khong_the_duyet_tag_chua_map(db_session):
    m = ItestTopicMap(itest_tag="Đề lạc", status="chua_map")
    db_session.add(m)
    await db_session.flush()
    with pytest.raises(ValueError):
        await mapping.approve_mapping(db_session, m.id)

"""US-23: gợi ý câu Itest theo ô ma trận — đúng ô, chỉ câu đã duyệt, dedupe,
báo thiếu. Match/rank/dedupe là code deterministic."""

import pytest
from sqlalchemy import select

from app.db.models import CurriculumTopic, Grade, ItestQuestion, ItestTopicMap, Subject
from app.exam.itest_suggest import (
    SuggestCell,
    phan_bo,
    suggest_cho_hoc_sinh,
    suggest_for_cells,
)


def test_phan_bo_tong_luon_khop():
    assert sum(phan_bo({"a": 1, "b": 1, "c": 1}, 10).values()) == 10
    assert phan_bo({"a": 3, "b": 1}, 4) == {"a": 3, "b": 1}
    assert phan_bo({}, 5) == {}


async def _seed_topic(session):
    subject = await session.scalar(select(Subject).filter_by(name="Toán")) or Subject(name="Toán")
    grade = await session.scalar(select(Grade).filter_by(name="Lớp 6")) or Grade(name="Lớp 6")
    session.add_all([subject, grade])
    await session.flush()
    topic = CurriculumTopic(subject_id=subject.id, grade_id=grade.id,
                            mach_noi_dung="Số", don_vi_kien_thuc="Số nguyên tố", order_index=1)
    session.add(topic)
    await session.flush()
    return topic


def _q(itest_id, tag, hash_, noi_dung="câu hỏi"):
    return ItestQuestion(itest_id=itest_id, tag_goc=tag, question_type="MC",
                         noi_dung=noi_dung, content_hash=hash_,
                         options_json='["a","b","c"]')


async def test_suggest_dung_o_va_chi_cau_da_duyet(db_session):
    topic = await _seed_topic(db_session)
    db_session.add_all([
        # tag đã duyệt, đúng topic + mức "trung_binh"
        ItestTopicMap(itest_tag="Đề duyệt", topic_id=topic.id, muc_do="trung_binh", status="da_duyet"),
        # tag cùng topic nhưng CHỜ duyệt -> không được gợi ý
        ItestTopicMap(itest_tag="Đề chờ", topic_id=topic.id, muc_do="trung_binh", status="cho_duyet"),
        _q("d1", "Đề duyệt", "h1"),
        _q("d2", "Đề duyệt", "h2"),
        _q("c1", "Đề chờ", "h3"),
    ])
    await db_session.flush()

    out = await suggest_for_cells(db_session, [
        SuggestCell(topic_id=topic.id, muc_do="trung_binh", so_cau_can=2)
    ])

    assert len(out) == 1
    ids = {u.itest_id for u in out[0].ung_vien}
    assert ids == {"d1", "d2"}        # chỉ câu đã duyệt
    assert out[0].con_thieu == 0


async def test_suggest_dedupe_theo_content_hash(db_session):
    topic = await _seed_topic(db_session)
    db_session.add_all([
        ItestTopicMap(itest_tag="Đề A", topic_id=topic.id, muc_do="de", status="da_duyet"),
        _q("a1", "Đề A", "same"),
        _q("a2", "Đề A", "same"),   # trùng nội dung (cùng hash) -> dedupe
        _q("a3", "Đề A", "khac"),
    ])
    await db_session.flush()

    out = await suggest_for_cells(db_session, [
        SuggestCell(topic_id=topic.id, muc_do="de", so_cau_can=3)
    ])
    hashes = len(out[0].ung_vien)
    assert hashes == 2                 # a1/a2 gộp còn 1, + a3
    assert out[0].con_thieu == 1       # cần 3, chỉ có 2 -> thiếu 1


async def test_suggest_bao_thieu_khi_ngan_hang_khong_du(db_session):
    topic = await _seed_topic(db_session)
    db_session.add_all([
        ItestTopicMap(itest_tag="Đề B", topic_id=topic.id, muc_do="kho", status="da_duyet"),
        _q("b1", "Đề B", "hb1"),
    ])
    await db_session.flush()

    out = await suggest_for_cells(db_session, [
        SuggestCell(topic_id=topic.id, muc_do="kho", so_cau_can=5)
    ])
    assert out[0].con_thieu == 4       # báo rõ thiếu, KHÔNG bịa câu cho đủ


# ── Gợi ý bài tập/đề Itest cho học sinh (chat) ──
# Dùng từ khoá độc nhất "zzkam" để không đụng dữ liệu Itest thật có thể đã sync.

async def test_suggest_hoc_sinh_match_theo_tu_khoa(db_session):
    db_session.add_all([
        ItestQuestion(itest_id="z1", tag_goc="Luyện tập - Chủ đề Zzkam đặc biệt",
                      question_type="MC", noi_dung="Câu Zzkam 1", content_hash="zh1",
                      options_json='["a","b"]'),
        ItestQuestion(itest_id="z2", tag_goc="Luyện tập - Chủ đề Zzkam đặc biệt",
                      question_type="MC", noi_dung="Câu Zzkam 2", content_hash="zh2"),
    ])
    await db_session.flush()

    g = await suggest_cho_hoc_sinh(db_session, "em muốn ôn tập về Zzkam")
    assert g is not None
    assert "Luyện tập - Chủ đề Zzkam đặc biệt" in g.de
    assert {b.itest_id for b in g.bai_tap} == {"z1", "z2"}


async def test_suggest_hoc_sinh_khong_co_tu_khoa_thi_none(db_session):
    # Toàn từ dừng/ngắn -> không trích được từ khoá -> không gợi ý lung tung.
    assert await suggest_cho_hoc_sinh(db_session, "em có") is None


async def test_suggest_hoc_sinh_khong_khop_thi_none(db_session):
    assert await suggest_cho_hoc_sinh(db_session, "Zzkhongtontai9999 xyz") is None

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import Blueprint, BlueprintCell, Book, CurriculumTopic, Grade, Subject, User


async def _seed_subject_grade(db_session):
    """Tên DUY NHẤT mỗi lần: fixture db_session dùng chung DB dev, mà
    subjects.name / grades.name là UNIQUE — chèn cứng "Toán"/"Lớp 6" sẽ đụng dữ
    liệu thật và đỏ oan chứ không phải lỗi model."""
    subject = Subject(name=f"Toán-{uuid.uuid4().hex[:6]}")
    grade = Grade(name=f"Lớp 6-{uuid.uuid4().hex[:6]}")
    db_session.add_all([subject, grade])
    await db_session.flush()
    return subject, grade


async def test_tao_book_gan_dung_subject_grade(db_session):
    subject, grade = await _seed_subject_grade(db_session)
    book = Book(
        name="Toán 6 - Cùng khám phá - Tập 1",
        subject_id=subject.id,
        grade_id=grade.id,
        semester="hk1",
        source_ref="cung_kham_pha_tap_1",
    )
    db_session.add(book)
    await db_session.flush()

    result = await db_session.execute(select(Book).where(Book.source_ref == "cung_kham_pha_tap_1"))
    saved = result.scalar_one()
    assert saved.subject_id == subject.id
    assert saved.grade_id == grade.id


async def test_book_trung_source_ref_bi_chan(db_session):
    subject, grade = await _seed_subject_grade(db_session)
    db_session.add(
        Book(name="A", subject_id=subject.id, grade_id=grade.id, semester="hk1", source_ref="dup")
    )
    await db_session.flush()

    db_session.add(
        Book(name="B", subject_id=subject.id, grade_id=grade.id, semester="hk2", source_ref="dup")
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_curriculum_topic_la_cau_noi_sgk_va_ma_tran(db_session):
    subject, grade = await _seed_subject_grade(db_session)
    topic = CurriculumTopic(
        subject_id=subject.id,
        grade_id=grade.id,
        mach_noi_dung="Số tự nhiên",
        don_vi_kien_thuc="Số tự nhiên và tập hợp các số tự nhiên",
        order_index=1,
    )
    db_session.add(topic)
    await db_session.flush()

    blueprint = Blueprint(subject_id=subject.id, grade_id=grade.id, semester="hk1")
    db_session.add(blueprint)
    await db_session.flush()

    cell = BlueprintCell(
        blueprint_id=blueprint.id,
        muc_do="de",
        nang_luc="Năng lực Giải quyết vấn đề toán học",
        yeu_cau_can_dat="Nhận biết được tập hợp các số tự nhiên",
        topic_id=topic.id,
        dang_thuc="Trắc nghiệm khách quan",
        ti_le=15.0,
        nhom_ti_le=1,
    )
    db_session.add(cell)
    await db_session.flush()

    assert cell.so_cau is None  # để trống tới khi build_blueprint tính


async def test_user_email_phai_duy_nhat(db_session):
    db_session.add(User(email="a@vd.vn", password_hash="x", name="A", role="hoc_sinh"))
    await db_session.flush()

    db_session.add(User(email="a@vd.vn", password_hash="y", name="B", role="giao_vien"))
    with pytest.raises(IntegrityError):
        await db_session.flush()

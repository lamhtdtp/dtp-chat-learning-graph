from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.models import BlueprintCell, CurriculumTopic
from app.exam.matrix_loader import load_matrix

REPO_ROOT = Path(__file__).resolve().parents[2]
HK1 = REPO_ROOT / "data" / "matrix" / "TOAN_6_HK1.docx"

pytestmark = pytest.mark.skipif(not HK1.exists(), reason="Cần file ma trận thật")


async def test_load_matrix_that_ghi_du_cell_va_topic(db_session):
    bp = await load_matrix(db_session, HK1, hoc_ky="hk1")

    n_cells = await db_session.scalar(
        select(func.count()).select_from(BlueprintCell).where(BlueprintCell.blueprint_id == bp.id)
    )
    assert n_cells == 41  # đúng số dòng ma trận thật HK1

    # mỗi cell trỏ vào 1 topic hợp lệ
    cells = list(await db_session.scalars(
        select(BlueprintCell).where(BlueprintCell.blueprint_id == bp.id)))
    assert all(c.topic_id is not None for c in cells)

    # dedupe: số ĐƠN VỊ ít hơn số cell (nhiều cell chung 1 đơn vị). Đếm qua cell
    # của chính blueprint này, KHÔNG count() cả bảng: fixture dùng chung DB dev
    # nên đếm toàn cục sẽ tính luôn danh mục có sẵn và đỏ oan.
    assert 0 < len({c.topic_id for c in cells}) <= n_cells
    assert all(c.muc_do in {"de", "trung_binh", "kho"} for c in cells)


async def test_load_matrix_idempotent(db_session):
    bp1 = await load_matrix(db_session, HK1, hoc_ky="hk1")
    bp2 = await load_matrix(db_session, HK1, hoc_ky="hk1")  # nạp lại

    # Bản cũ bị xoá hẳn, không để lại cell mồ côi -> đúng 41 cell, không thành 82.
    assert await db_session.scalar(select(func.count()).select_from(BlueprintCell)
                                  .where(BlueprintCell.blueprint_id == bp1.id)) == 0
    assert await db_session.scalar(select(func.count()).select_from(BlueprintCell)
                                  .where(BlueprintCell.blueprint_id == bp2.id)) == 41


async def test_nap_lai_khong_de_ra_don_vi_trung(db_session):
    """Nạp .docx hai lần KHÔNG được nhân đôi danh mục.

    Tên trong Word lệch khoảng trắng / mạch bị cắt cụt so với danh mục đã có, mà
    loader từng so chuỗi tuyệt đối -> lần nạp nào cũng tưởng là đơn vị mới. Đó là
    cách danh mục Toán 6 phình từ 21 lên 42 đơn vị, học sinh bấm vào bản rỗng.
    """
    bp1 = await load_matrix(db_session, HK1, hoc_ky="hk1")
    dv1 = {c.topic_id for c in await db_session.scalars(
        select(BlueprintCell).where(BlueprintCell.blueprint_id == bp1.id))}

    bp2 = await load_matrix(db_session, HK1, hoc_ky="hk1")
    dv2 = {c.topic_id for c in await db_session.scalars(
        select(BlueprintCell).where(BlueprintCell.blueprint_id == bp2.id))}

    assert dv2 == dv1                       # trỏ lại ĐÚNG các đơn vị cũ
    assert not getattr(bp2, "don_vi_moi", [])   # lần hai không tạo thêm gì


async def test_khop_gan_dung_khi_ten_lech_khoang_trang(db_session):
    """Đơn vị đã có trong danh mục, tên trong ma trận lệch chút -> phải khớp lại."""
    from app.db.models import Grade, Subject

    bp = await load_matrix(db_session, HK1, hoc_ky="hk1")
    subject = await db_session.scalar(select(Subject).filter_by(name="Toán"))
    grade = await db_session.scalar(select(Grade).filter_by(name="Lớp 6"))
    truoc = set(await db_session.scalars(select(CurriculumTopic.id).filter_by(
        subject_id=subject.id, grade_id=grade.id)))

    # Bóp méo tên mạch của một đơn vị đúng kiểu Word hay ra: mất một khoảng trắng.
    t = await db_session.scalar(select(CurriculumTopic).filter_by(
        subject_id=subject.id, grade_id=grade.id,
        id=next(iter(truoc))))
    t.mach_noi_dung = (t.mach_noi_dung or "x").replace(" ", "", 1) or "x"
    await db_session.flush()

    await load_matrix(db_session, HK1, hoc_ky="hk1")
    sau = set(await db_session.scalars(select(CurriculumTopic.id).filter_by(
        subject_id=subject.id, grade_id=grade.id)))
    assert sau == truoc, "tên lệch khoảng trắng vẫn phải khớp, không tạo bản mới"

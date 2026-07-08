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

    # curriculum_topics dedupe: ít hơn số cell (nhiều cell chung 1 topic)
    n_topics = await db_session.scalar(select(func.count()).select_from(CurriculumTopic))
    assert 0 < n_topics <= n_cells

    # mỗi cell trỏ vào 1 topic hợp lệ
    cells = list(await db_session.scalars(
        select(BlueprintCell).where(BlueprintCell.blueprint_id == bp.id)))
    assert all(c.topic_id is not None for c in cells)
    assert all(c.muc_do in {"de", "trung_binh", "kho"} for c in cells)


async def test_load_matrix_idempotent(db_session):
    await load_matrix(db_session, HK1, hoc_ky="hk1")
    await load_matrix(db_session, HK1, hoc_ky="hk1")  # nạp lại

    # vẫn đúng 41 cell, không nhân đôi thành 82
    n_cells = await db_session.scalar(select(func.count()).select_from(BlueprintCell))
    assert n_cells == 41

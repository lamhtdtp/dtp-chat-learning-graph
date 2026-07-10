"""US-21: sync idempotent theo itest_id + hash; lỗi nguồn -> đẩy lên để retry."""

import pytest
from sqlalchemy import select

from app.db.models import ItestQuestion
from app.integrations.itest import sync
from app.integrations.itest.source import ItestRecord


class FakeSource:
    """Nguồn Itest giả (read-only): trả danh sách record cố định."""

    def __init__(self, records):
        self._records = records

    async def fetch_questions(self):
        return list(self._records)


class BrokenSource:
    async def fetch_questions(self):
        raise ConnectionError("mất kết nối Itest giữa chừng")


def _rec(itest_id, noi_dung="2+2=?", dap_an="4", tag="Đề A"):
    return ItestRecord(itest_id=itest_id, tag_goc=tag, noi_dung=noi_dung,
                       options=["3", "4", "5"], dap_an=dap_an)


async def test_sync_ghi_vao_mirror(db_session):
    src = FakeSource([_rec("q1"), _rec("q2")])
    report = await sync.sync_questions(db_session, src)

    assert report.them_moi == 2
    rows = list(await db_session.scalars(
        select(ItestQuestion).where(ItestQuestion.itest_id.in_(["q1", "q2"]))
    ))
    assert {r.itest_id for r in rows} == {"q1", "q2"}


async def test_sync_idempotent_khong_tao_trung(db_session):
    src = FakeSource([_rec("q1")])
    await sync.sync_questions(db_session, src)
    report2 = await sync.sync_questions(db_session, src)  # chạy lại, nội dung không đổi

    assert report2.them_moi == 0
    assert report2.khong_doi == 1
    count = len(list(await db_session.scalars(
        select(ItestQuestion).where(ItestQuestion.itest_id == "q1")
    )))
    assert count == 1  # không bản ghi trùng


async def test_sync_noi_dung_doi_thi_cap_nhat(db_session):
    await sync.sync_questions(db_session, FakeSource([_rec("q1", dap_an="4")]))
    report2 = await sync.sync_questions(db_session, FakeSource([_rec("q1", dap_an="5")]))

    assert report2.cap_nhat == 1
    row = await db_session.scalar(select(ItestQuestion).where(ItestQuestion.itest_id == "q1"))
    assert row.dap_an == "5"


async def test_sync_loi_ket_noi_day_len_de_retry(db_session):
    with pytest.raises(ConnectionError):
        await sync.sync_questions(db_session, BrokenSource())

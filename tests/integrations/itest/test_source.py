"""US-21 Scenario 3: read-only tuyệt đối + parse câu hỏi thô từ nguồn Itest."""

import pytest

from app.integrations.itest.source import (
    DbItestSource,
    ReadOnlyViolation,
    _row_to_record,
    _split_options,
)


def test_split_options_ngan_bang_sao_va_thang():
    assert _split_options("A*B*C*D") == ["A", "B", "C", "D"]
    assert _split_options("Đúng#Sai") == ["Đúng", "Sai"]
    assert _split_options("chỉ một") == ["chỉ một"]


def test_row_to_record_lam_sach_html():
    rec = _row_to_record({
        "unit_test_id": 7, "tag_goc": "Đề KT Số nguyên",
        "question_id": 42, "question_type": "mc",
        "question_description": "<p>2 + 3 = ?</p>",
        "answers": "4*5*6*7", "correct_answers": "5", "image": None,
    })
    assert rec is not None
    assert rec.itest_id == "42"
    assert rec.noi_dung == "2 + 3 = ?"
    assert rec.options == ["4", "5", "6", "7"]
    assert rec.question_type == "MC"


def test_content_hash_on_dinh_va_doi_theo_noi_dung():
    base = dict(itest_id="1", tag_goc="t", noi_dung="q", options=["a", "b"], dap_an="a")
    from app.integrations.itest.source import ItestRecord

    r1 = ItestRecord(**base)
    r2 = ItestRecord(**base)
    r3 = ItestRecord(**{**base, "dap_an": "b"})
    assert r1.content_hash() == r2.content_hash()   # tất định
    assert r1.content_hash() != r3.content_hash()   # đổi nội dung -> đổi hash


def test_select_chan_moi_lenh_ghi():
    """Cửa DB Itest chỉ nhận SELECT — mọi lệnh ghi bị chặn ngay, không cần DB thật."""
    src = DbItestSource(database_url="mysql+pymysql://x")  # không kết nối thật
    for bad in ["UPDATE question SET x=1", "DELETE FROM question", "insert into q values(1)", "DROP TABLE q"]:
        with pytest.raises(ReadOnlyViolation):
            src._select(bad, {})

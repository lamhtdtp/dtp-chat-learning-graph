from pathlib import Path

import pytest

from app.ingestion.matrix_parser import (
    MatrixRow,
    normalize_muc_do,
    parse_matrix_docx,
    parse_matrix_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HK1_PATH = REPO_ROOT / "data" / "matrix" / "TOAN_6_HK1.docx"
HK2_PATH = REPO_ROOT / "data" / "matrix" / "TOAN_6_HK2.docx"


def test_forward_fill_o_gop_doc():
    raw = [
        [
            "Dễ (Biết)",
            "Năng lực A",
            "Biểu hiện A",
            "Nhận biết tập hợp số tự nhiên",
            "Số tự nhiên",
            "Đơn vị 1",
            "Trắc nghiệm",
            "15",
        ],
        ["", "", "", "Nhận biết thứ tự phép tính", "", "Đơn vị 2", "", ""],
    ]
    recs = parse_matrix_rows(raw)

    assert recs[1].muc_do == "de"
    assert recs[1].mach_noi_dung == "Số tự nhiên"
    assert recs[1].nang_luc_thanh_phan == "Năng lực A"
    assert recs[1].ti_le == 15.0
    # cột KHÔNG merge (yêu cầu cần đạt, đơn vị kiến thức) phải giữ giá trị riêng, không bị ghi đè
    assert recs[1].yeu_cau_can_dat == "Nhận biết thứ tự phép tính"
    assert recs[1].don_vi_kien_thuc == "Đơn vị 2"


def test_forward_fill_bao_loi_khi_thieu_gia_tri_dau():
    with pytest.raises(ValueError):
        parse_matrix_rows([["", "A", "B", "C", "D", "E", "F", "10"]])


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Dễ\n(Biết)", "de"),
        ("Dễ (Biết)", "de"),
        ("Trung bình (Hiểu)", "trung_binh"),
        ("Khó (Vận dụng)", "kho"),
    ],
)
def test_normalize_muc_do(raw, expected):
    assert normalize_muc_do(raw) == expected


def test_normalize_muc_do_khong_nhan_dien_duoc():
    with pytest.raises(ValueError):
        normalize_muc_do("???")


@pytest.mark.skipif(not HK1_PATH.exists(), reason="Cần file ma trận thật data/matrix/TOAN_6_HK1.docx")
def test_parse_real_hk1():
    records = parse_matrix_docx(HK1_PATH)

    assert len(records) == 41
    assert all(isinstance(r, MatrixRow) for r in records)
    assert all(r.muc_do in {"de", "trung_binh", "kho"} for r in records)
    assert all(r.ti_le > 0 for r in records)

    first = records[0]
    assert first.muc_do == "de"
    assert first.mach_noi_dung == "Số tự nhiên"
    assert first.yeu_cau_can_dat == "Nhận biết được tập hợp các số tự nhiên"
    assert first.ti_le == 15.0


@pytest.mark.skipif(not HK2_PATH.exists(), reason="Cần file ma trận thật data/matrix/TOAN_6_HK2.docx")
def test_parse_real_hk2():
    records = parse_matrix_docx(HK2_PATH)

    assert len(records) == 37
    assert all(r.muc_do in {"de", "trung_binh", "kho"} for r in records)
    assert all(r.ti_le > 0 for r in records)

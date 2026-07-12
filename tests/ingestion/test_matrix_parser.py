from pathlib import Path

import pytest

from app.ingestion.matrix_parser import (
    MatrixRow,
    normalize_muc_do,
    parse_matrix_docx,
    parse_matrix_rows,
    tong_ti_le_theo_muc_do,
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
    # dòng 2 kế thừa tỉ lệ từ dòng 1 (ô Tỉ lệ % rỗng) => cùng 1 nhóm, không phải nhóm mới
    assert recs[1].nhom_ti_le == recs[0].nhom_ti_le


def test_tong_ti_le_khong_cong_trung_khi_gop_nhom():
    raw = [
        ["Dễ (Biết)", "NL", "BH", "YCCD 1", "Số tự nhiên", "DVKT 1", "TN", "15"],
        ["", "", "", "YCCD 2", "", "DVKT 2", "", ""],
        ["", "", "", "YCCD 3", "", "DVKT 3", "", ""],
        ["Trung bình (Hiểu)", "NL", "BH", "YCCD 4", "Số nguyên", "DVKT 4", "TN", "20"],
    ]
    recs = parse_matrix_rows(raw)

    # 3 dòng đầu CÙNG 1 nhóm 15% (không phải 15+15+15=45)
    assert tong_ti_le_theo_muc_do(recs) == {"de": 15.0, "trung_binh": 20.0}


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

    # Bất biến quan trọng nhất: tổng tỉ lệ toàn ma trận PHẢI đúng 100%, tính
    # theo nhóm (không cộng trùng dòng nào dùng chung 1 mức tỉ lệ).
    tong = tong_ti_le_theo_muc_do(records)
    assert tong == {"de": 40.0, "trung_binh": 30.0, "kho": 30.0}
    assert sum(tong.values()) == 100.0


@pytest.mark.skipif(not HK2_PATH.exists(), reason="Cần file ma trận thật data/matrix/TOAN_6_HK2.docx")
def test_parse_real_hk2():
    records = parse_matrix_docx(HK2_PATH)

    assert len(records) == 37
    assert all(r.muc_do in {"de", "trung_binh", "kho"} for r in records)
    assert all(r.ti_le > 0 for r in records)

    tong = tong_ti_le_theo_muc_do(records)
    assert tong == {"de": 40.0, "trung_binh": 30.0, "kho": 30.0}
    assert sum(tong.values()) == 100.0


# ── Parser .md (Tiếng Anh) ──
_MD = """# Ma trận
| STT | Mức độ | Năng lực | Biểu hiện | Yêu cầu cần đạt | Mạch nội dung | Đơn vị kiến thức | Dạng thức | Tỉ lệ % | Số câu |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Dễ (Biết) | Ngữ âm | Nhận biết âm | YC âm | School | Phát âm | TN | 5 |  |
| 2 | Dễ (Biết) | Từ vựng | Nhận biết từ | YC vocab Home | Home | Vocab rooms | TN | 10 |  |
| 3 | Dễ (Biết) | Từ vựng | Nhận biết từ | YC vocab School | School | Vocab subjects | TN | 10 |  |
| 4 | Trung bình (Hiểu) | Từ vựng | Hiểu từ | YC ngữ cảnh | School | Vocab context | TN | 30 |  |
| 5 | Khó (Vận dụng) | Viết | Viết câu | YC sắp xếp | Home | Writing build | TL | 25 |  |
| 6 | Khó (Vận dụng) | Viết | Viết lại | YC viết lại | Friends | Writing rewrite | TL | 20 |  |

## Tổng hợp
| Mức độ | Tổng % |
|---|---|
| Dễ | 25 |
"""


def test_parse_matrix_md_gop_nhom_lien_nhau(tmp_path):
    f = tmp_path / "m.md"
    f.write_text(_MD, encoding="utf-8")
    from app.ingestion.matrix_parser import parse_matrix_md
    rows = parse_matrix_md(f)
    assert len(rows) == 6                       # chỉ bảng ma trận, không lấy bảng tổng hợp
    # dòng 2,3 (Dễ/Từ vựng/Nhận biết từ) cùng nhóm; 5,6 (Khó/Viết/khác biểu hiện) KHÁC nhóm
    assert rows[1].nhom_ti_le == rows[2].nhom_ti_le
    assert rows[4].nhom_ti_le != rows[5].nhom_ti_le
    tot = tong_ti_le_theo_muc_do(rows)
    # Dễ: 5 + 10 (nhóm Từ vựng tính 1 lần) = 15; TB 30; Khó 25+20=45
    assert tot == {"de": 15.0, "trung_binh": 30.0, "kho": 45.0}


def test_parse_matrix_dispatch_theo_duoi(tmp_path):
    from app.ingestion.matrix_parser import parse_matrix, parse_matrix_md
    f = tmp_path / "m.md"
    f.write_text(_MD, encoding="utf-8")
    assert [r.model_dump() for r in parse_matrix(f)] == [r.model_dump() for r in parse_matrix_md(f)]

from pathlib import Path

import pytest

from app.exam.blueprint import build_blueprint
from app.ingestion.matrix_parser import parse_matrix_docx, tong_ti_le_theo_muc_do

REPO_ROOT = Path(__file__).resolve().parents[2]
HK1_PATH = REPO_ROOT / "data" / "matrix" / "TOAN_6_HK1.docx"


@pytest.mark.skipif(not HK1_PATH.exists(), reason="Cần file ma trận thật data/matrix/TOAN_6_HK1.docx")
def test_build_blueprint_tu_ma_tran_that_hk1():
    records = parse_matrix_docx(HK1_PATH)
    ti_le = tong_ti_le_theo_muc_do(records)

    bp = build_blueprint(ti_le, tong_so_cau=20)

    assert sum(bp.values()) == 20
    assert bp == {"de": 8, "trung_binh": 6, "kho": 6}

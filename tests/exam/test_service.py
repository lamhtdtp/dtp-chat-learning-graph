"""Test hàm thuần của service sinh đề (không cần DB/LLM)."""

from types import SimpleNamespace

from app.exam.service import _ti_le_theo_muc_do


def _cell(muc_do: str, ti_le: float, nhom: int):
    return SimpleNamespace(muc_do=muc_do, ti_le=ti_le, nhom_ti_le=nhom)


def test_ti_le_moi_nhom_chi_tinh_mot_lan():
    # 3 dòng cùng nhóm 0 (mức dễ, 40%) không được cộng 3 lần thành 120%.
    cells = [
        _cell("de", 40.0, 0),
        _cell("de", 40.0, 0),
        _cell("de", 40.0, 0),
        _cell("trung_binh", 35.0, 1),
        _cell("kho", 25.0, 2),
    ]
    assert _ti_le_theo_muc_do(cells) == {"de": 40.0, "trung_binh": 35.0, "kho": 25.0}


def test_ti_le_cong_don_nhieu_nhom_cung_muc_do():
    cells = [_cell("de", 20.0, 0), _cell("de", 20.0, 1)]
    assert _ti_le_theo_muc_do(cells) == {"de": 40.0}

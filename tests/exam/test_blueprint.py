from app.exam.blueprint import build_blueprint


def test_blueprint_khong_mat_cau_do_lam_tron():
    ti_le = {"de": 40, "trung_binh": 35, "kho": 25}
    bp = build_blueprint(ti_le, tong_so_cau=10)
    assert sum(bp.values()) == 10


def test_blueprint_dung_largest_remainder_khi_hoa_le():
    # de=4.0 (chẵn); trung_binh=3.5 và kho=2.5 hoà phần dư 0.5 => 1 trong 2 được +1
    ti_le = {"de": 40, "trung_binh": 35, "kho": 25}
    bp = build_blueprint(ti_le, tong_so_cau=10)
    assert bp["de"] == 4
    assert bp["trung_binh"] + bp["kho"] == 6


def test_blueprint_khop_ti_le_chuan_ctgdpt_2018():
    # Biết 40% / Hiểu 30% / Vận dụng 30% — đúng số liệu thật từ TOAN_6_HK1/HK2
    ti_le = {"de": 40.0, "trung_binh": 30.0, "kho": 30.0}
    bp = build_blueprint(ti_le, tong_so_cau=20)
    assert bp == {"de": 8, "trung_binh": 6, "kho": 6}


def test_blueprint_tong_so_cau_khong_chia_het_van_khop_tong():
    ti_le = {"de": 40.0, "trung_binh": 30.0, "kho": 30.0}
    bp = build_blueprint(ti_le, tong_so_cau=7)
    assert sum(bp.values()) == 7

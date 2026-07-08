from app.exam.check import CauHoi, DeThi, kiem_tra_ti_le, tinh_phan_thieu


def make_de(so_cau_de: int = 0, so_cau_trung_binh: int = 0, so_cau_kho: int = 0) -> DeThi:
    cau_hoi = (
        [CauHoi(muc_do="de")] * so_cau_de
        + [CauHoi(muc_do="trung_binh")] * so_cau_trung_binh
        + [CauHoi(muc_do="kho")] * so_cau_kho
    )
    return DeThi(cau_hoi=cau_hoi)


def test_check_phat_hien_sai_phan_bo():
    de = make_de(so_cau_de=3, so_cau_kho=0)
    chi_tieu = {"de": 4, "kho": 2}

    assert kiem_tra_ti_le(de, chi_tieu) is False
    assert tinh_phan_thieu(de, chi_tieu) == {"de": 1, "kho": 2}


def test_check_dat_khi_du_hoac_thua_chi_tieu():
    de = make_de(so_cau_de=4, so_cau_trung_binh=3, so_cau_kho=3)
    chi_tieu = {"de": 4, "trung_binh": 3, "kho": 2}  # thừa 1 câu kho vẫn đạt

    assert kiem_tra_ti_le(de, chi_tieu) is True
    assert tinh_phan_thieu(de, chi_tieu) == {}

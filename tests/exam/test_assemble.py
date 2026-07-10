"""US-24: trộn Itest + AI giữ attribution, kiểm khớp ma trận trên bộ trộn, giữ
nguồn khi xuất, luồng SGK-only không đổi."""

from app.exam.assemble import (
    assemble_bo_luyen,
    export_rows,
    kiem_tra_khop_ma_tran,
)


def test_tron_hai_nguon_gan_dung_nguon():
    bo = assemble_bo_luyen(
        itest_picks=[{"itest_id": "q7", "muc_do": "de", "noi_dung": "1+1=?"}],
        ai_cau=[{"muc_do": "kho", "noi_dung": "chứng minh..."}],
    )
    assert len(bo.cau_hoi) == 2
    nguon = {c.nguon for c in bo.cau_hoi}
    assert nguon == {"itest:q7", "ai"}


def test_kiem_tra_khop_ma_tran_tren_bo_tron():
    bo = assemble_bo_luyen(
        itest_picks=[{"itest_id": "1", "muc_do": "de"}, {"itest_id": "2", "muc_do": "de"}],
        ai_cau=[{"muc_do": "kho"}],
    )
    report = kiem_tra_khop_ma_tran(bo, {"de": 2, "trung_binh": 1, "kho": 1})
    assert report.dem["de"] == 2
    assert report.thieu == {"trung_binh": 1}   # cảnh báo ô thiếu bất kể nguồn
    assert report.khop is False


def test_kiem_tra_bao_thua():
    bo = assemble_bo_luyen(ai_cau=[{"muc_do": "de"}, {"muc_do": "de"}, {"muc_do": "de"}])
    report = kiem_tra_khop_ma_tran(bo, {"de": 2})
    assert report.thua == {"de": 1}


def test_export_giu_attribution():
    bo = assemble_bo_luyen(itest_picks=[{"itest_id": "abc", "muc_do": "de", "noi_dung": "x"}])
    rows = export_rows(bo)
    assert rows[0]["itest_id"] == "abc"
    assert rows[0]["nguon"] == "itest:abc"


def test_luong_sgk_only_khong_phu_thuoc_itest():
    """Chỉ dùng câu AI-sinh -> bộ luyện vẫn lắp bình thường, Itest là tuỳ chọn."""
    bo = assemble_bo_luyen(ai_cau=[{"muc_do": "de"}, {"muc_do": "kho"}])
    assert len(bo.cau_hoi) == 2
    assert all(c.nguon == "ai" for c in bo.cau_hoi)
    assert kiem_tra_khop_ma_tran(bo, {"de": 1, "kho": 1}).khop is True

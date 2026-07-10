"""Lắp bộ luyện: trộn câu Itest + câu AI-sinh, GIỮ NGUỒN từng câu (EPIC-10,
US-24).

Itest là luồng song song với đề tự sinh SGK — học sinh tự chọn/trộn. Bộ luyện
giữ attribution (`nguon = "itest:<id>"` | `"ai"`) để minh bạch & tôn trọng bản
quyền Itest. Kiểm khớp ma trận chạy trên bộ ĐÃ TRỘN, đếm bất kể nguồn (tái dùng
app.exam.check). Luồng exam_gen từ SGK KHÔNG đổi — Itest chỉ là tuỳ chọn thêm.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.exam.check import CauHoi, DeThi, dem_cau_theo_muc_do, tinh_phan_thieu


class CauLuyen(BaseModel):
    nguon: str  # "itest:<itest_id>" | "ai"
    muc_do: str
    noi_dung: str
    options: list[str] = []
    dap_an: str = ""
    loi_giai: str = ""
    itest_id: str | None = None  # giữ để đối soát bản quyền Itest


class BoLuyen(BaseModel):
    cau_hoi: list[CauLuyen]


class MaTranReport(BaseModel):
    dem: dict[str, int]
    thieu: dict[str, int]
    thua: dict[str, int]
    khop: bool


def assemble_bo_luyen(
    itest_picks: list[dict] | None = None, ai_cau: list[dict] | None = None
) -> BoLuyen:
    """Trộn câu Itest học sinh chọn + câu AI-sinh thành 1 bộ luyện, gắn nguồn.
    Cả hai đều tuỳ chọn (chỉ AI = luồng SGK thuần, không phụ thuộc Itest)."""
    cau: list[CauLuyen] = []
    for c in itest_picks or []:
        cau.append(CauLuyen(
            nguon=f"itest:{c['itest_id']}", itest_id=str(c["itest_id"]),
            muc_do=c["muc_do"], noi_dung=c.get("noi_dung", ""),
            options=c.get("options", []), dap_an=c.get("dap_an", ""),
            loi_giai=c.get("loi_giai", ""),
        ))
    for c in ai_cau or []:
        cau.append(CauLuyen(
            nguon="ai", muc_do=c["muc_do"], noi_dung=c.get("noi_dung", ""),
            options=c.get("options", []), dap_an=c.get("dap_an", ""),
            loi_giai=c.get("loi_giai", ""),
        ))
    return BoLuyen(cau_hoi=cau)


def kiem_tra_khop_ma_tran(bo: BoLuyen, chi_tieu: dict[str, int]) -> MaTranReport:
    """Đếm theo mức độ trên bộ ĐÃ TRỘN (bất kể nguồn) và so blueprint; cảnh báo
    ô thiếu/thừa."""
    de = DeThi(cau_hoi=[CauHoi(muc_do=c.muc_do) for c in bo.cau_hoi])
    dem = dem_cau_theo_muc_do(de)
    thieu = tinh_phan_thieu(de, chi_tieu)
    thua = {
        m: dem.get(m, 0) - so
        for m, so in chi_tieu.items()
        if dem.get(m, 0) - so > 0
    }
    return MaTranReport(dem=dem, thieu=thieu, thua=thua, khop=not thieu and not thua)


def export_rows(bo: BoLuyen) -> list[dict]:
    """Xuất bộ luyện (bản in) — GIỮ nguồn/itest_id để đối soát bản quyền."""
    return [
        {"nguon": c.nguon, "itest_id": c.itest_id, "muc_do": c.muc_do,
         "noi_dung": c.noi_dung, "options": c.options, "dap_an": c.dap_an}
        for c in bo.cau_hoi
    ]

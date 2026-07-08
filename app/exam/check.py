"""Kiểm tra đề đã sinh có đúng ma trận không — đếm bằng code, KHÔNG hỏi LLM
"đề này đúng ma trận chưa" (xem skill exam-generation).
"""

from pydantic import BaseModel

from app.ingestion.matrix_parser import MucDo


class CauHoi(BaseModel):
    muc_do: MucDo
    noi_dung: str = ""
    dap_an: str = ""
    loi_giai: str = ""


class DeThi(BaseModel):
    cau_hoi: list[CauHoi]


def dem_cau_theo_muc_do(de: DeThi) -> dict[str, int]:
    counts: dict[str, int] = {"de": 0, "trung_binh": 0, "kho": 0}
    for cau in de.cau_hoi:
        counts[cau.muc_do] += 1
    return counts


def kiem_tra_ti_le(de: DeThi, chi_tieu: dict[str, int]) -> bool:
    counts = dem_cau_theo_muc_do(de)
    return all(counts.get(muc_do, 0) >= so_luong for muc_do, so_luong in chi_tieu.items())


def tinh_phan_thieu(de: DeThi, chi_tieu: dict[str, int]) -> dict[str, int]:
    """Chỉ trả về phần THIẾU (chi_tieu - thực tế), để exam_gen_node sinh bù
    đúng phần còn thiếu — không sinh lại từ đầu."""
    counts = dem_cau_theo_muc_do(de)
    thieu: dict[str, int] = {}
    for muc_do, so_luong in chi_tieu.items():
        con_thieu = so_luong - counts.get(muc_do, 0)
        if con_thieu > 0:
            thieu[muc_do] = con_thieu
    return thieu

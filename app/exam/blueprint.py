"""Quy đổi tỉ lệ % (theo mức độ) trong ma trận thành số câu thực tế.

Đếm/phân bổ là code deterministic — không giao việc này cho LLM (xem skill
exam-generation). Input là output của
`app.ingestion.matrix_parser.tong_ti_le_theo_muc_do`.
"""


def build_blueprint(ti_le_theo_muc_do: dict[str, float], tong_so_cau: int) -> dict[str, int]:
    """Largest-remainder: chia phần nguyên trước, phần dư (làm tròn xuống bị mất)
    chia cho các mục có phần thập phân lớn nhất, để tổng số câu LUÔN khớp chính
    xác `tong_so_cau` — không được để làm tròn độc lập từng mục làm lệch tổng.
    """
    so_cau_le: dict[str, float] = {
        muc_do: ti_le / 100 * tong_so_cau for muc_do, ti_le in ti_le_theo_muc_do.items()
    }
    so_cau: dict[str, int] = {muc_do: int(v) for muc_do, v in so_cau_le.items()}

    con_thieu = tong_so_cau - sum(so_cau.values())
    thu_tu_uu_tien = sorted(
        so_cau_le, key=lambda muc_do: so_cau_le[muc_do] - so_cau[muc_do], reverse=True
    )
    for muc_do in thu_tu_uu_tien[:con_thieu]:
        so_cau[muc_do] += 1

    return so_cau

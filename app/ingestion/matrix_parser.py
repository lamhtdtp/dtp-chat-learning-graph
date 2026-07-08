"""Parse ma trận đặc tả đề kiểm tra (.docx) thành dữ liệu có cấu trúc.

Ma trận là dữ liệu THIẾT KẾ đề (mức độ x mạch nội dung x tỉ lệ), khác hoàn toàn
SGK — không embed, không vào vector DB (xem skill data-ingestion). Đây là logic
deterministic, viết theo TDD (xem tests/ingestion/test_matrix_parser.py).
"""

from pathlib import Path
from typing import Literal

from docx import Document
from docx.oxml.ns import qn
from pydantic import BaseModel

MucDo = Literal["de", "trung_binh", "kho"]

# Số cột dữ liệu sau khi bỏ STT (cột 0) và Số câu (cột 9) của bảng ma trận thật.
_COLUMNS = (
    "muc_do",
    "nang_luc_thanh_phan",
    "bieu_hien_nang_luc",
    "yeu_cau_can_dat",
    "mach_noi_dung",
    "don_vi_kien_thuc",
    "dang_thuc",
    "ti_le",
)
_TI_LE_INDEX = _COLUMNS.index("ti_le")


class MatrixRow(BaseModel):
    muc_do: MucDo
    nang_luc_thanh_phan: str
    bieu_hien_nang_luc: str
    yeu_cau_can_dat: str
    mach_noi_dung: str
    don_vi_kien_thuc: str
    dang_thuc: str
    ti_le: float
    # Số thứ tự nhóm tỉ lệ (tăng dần theo dòng): nhiều "yêu cầu cần đạt" có thể
    # CÙNG chia sẻ một mức tỉ lệ chung (ô gộp dọc cho cả cụm) — dùng field này
    # để cộng tỉ lệ đúng 1 lần/nhóm (xem `tong_ti_le_theo_muc_do`), tránh cộng
    # trùng nếu cộng thẳng `ti_le` của từng dòng riêng lẻ.
    nhom_ti_le: int


def normalize_muc_do(raw: str) -> MucDo:
    text = raw.replace("\n", " ").strip().lower()
    if text.startswith("dễ"):
        return "de"
    if text.startswith("trung bình"):
        return "trung_binh"
    if text.startswith("khó"):
        return "kho"
    raise ValueError(f"Không nhận diện được mức độ: {raw!r}")


def parse_matrix_rows(rows: list[list[str]]) -> list[MatrixRow]:
    """Forward-fill ô gộp dọc rồi build MatrixRow cho từng dòng.

    `rows` là lưới text thô, mỗi dòng đúng thứ tự _COLUMNS (8 cột, đã bỏ STT/Số câu).
    Ô rỗng được coi là do gộp dọc, kế thừa giá trị của dòng gần nhất phía trên CÙNG
    CỘT — áp dụng chung cho mọi cột thay vì hardcode cột nào bị gộp, vì file ma trận
    thật (xem test_parse_real_hk1/hk2) không nhất quán cột nào có gộp giữa các
    trường/sách khác nhau.
    """
    if not rows:
        return []

    ncols = len(_COLUMNS)
    last_values: list[str | None] = [None] * ncols
    records: list[MatrixRow] = []
    nhom_ti_le = 0

    for row_idx, row in enumerate(rows):
        # Ô Tỉ lệ % không rỗng => dòng này mở một nhóm tỉ lệ mới (VD nhiều "yêu
        # cầu cần đạt" cùng dùng chung 1 mức tỉ lệ, chỉ dòng đầu nhóm có giá trị
        # thô, các dòng sau rỗng do gộp dọc). Phải xác định TRƯỚC khi forward-fill
        # ở dưới ghi đè ô rỗng này.
        if row[_TI_LE_INDEX].strip() != "":
            nhom_ti_le += 1
        elif nhom_ti_le == 0:
            raise ValueError(
                f"Dòng {row_idx}: cột 'ti_le' rỗng nhưng chưa có nhóm nào trước đó."
            )

        filled: list[str] = []
        for col_idx, raw_cell in enumerate(row):
            value = raw_cell.strip()
            if value == "":
                if last_values[col_idx] is None:
                    raise ValueError(
                        f"Dòng {row_idx}, cột '{_COLUMNS[col_idx]}' rỗng nhưng chưa "
                        "có giá trị nào phía trên để forward-fill."
                    )
                value = last_values[col_idx]
            last_values[col_idx] = value
            filled.append(value)

        (
            muc_do_raw,
            nang_luc,
            bieu_hien,
            yeu_cau,
            mach,
            don_vi,
            dang_thuc,
            ti_le_raw,
        ) = filled

        records.append(
            MatrixRow(
                muc_do=normalize_muc_do(muc_do_raw),
                nang_luc_thanh_phan=nang_luc,
                bieu_hien_nang_luc=bieu_hien,
                yeu_cau_can_dat=yeu_cau,
                mach_noi_dung=mach,
                don_vi_kien_thuc=don_vi,
                dang_thuc=dang_thuc,
                ti_le=float(ti_le_raw.replace(",", ".")),
                nhom_ti_le=nhom_ti_le,
            )
        )

    return records


def tong_ti_le_theo_muc_do(records: list[MatrixRow]) -> dict[str, float]:
    """Cộng tỉ lệ % theo mức độ, mỗi NHÓM (`nhom_ti_le`) chỉ tính một lần.

    Không được cộng thẳng `ti_le` của từng MatrixRow — nhiều "yêu cầu cần đạt"
    dùng chung một mức tỉ lệ sẽ bị nhân bản nhiều lần và ra tổng sai (đã kiểm
    chứng trên dữ liệu thật: cộng thẳng cho ra 85%/140% thay vì đúng 100%).
    """
    seen: set[int] = set()
    totals: dict[str, float] = {}
    for r in records:
        if r.nhom_ti_le in seen:
            continue
        seen.add(r.nhom_ti_le)
        totals[r.muc_do] = totals.get(r.muc_do, 0.0) + r.ti_le
    return totals


def _raw_row_texts(row) -> list[str]:
    """Text nguyên bản của từng ô trong 1 dòng, KHÔNG qua cơ chế tự resolve ô
    gộp dọc của python-docx.

    `row.cells[i].text` (API cấp cao) trả về giá trị đã "điền lại" cho ô gộp
    dọc dạng continue — kể cả `cell._tc` cũng đã bị trỏ sang `<w:tc>` gốc của
    nhóm merge, không phải `<w:tc>` cục bộ. Phải đọc thẳng `row._tr.tc_lst`
    (danh sách `<w:tc>` thật trong XML của dòng) để thấy đúng ô nào rỗng.
    """
    return [
        "".join(node.text or "" for node in tc.iter(qn("w:t"))).strip()
        for tc in row._tr.tc_lst
    ]


def parse_matrix_docx(path: str | Path) -> list[MatrixRow]:
    """Đọc bảng ma trận từ file .docx thật.

    Cấu trúc bảng thật (đã inspect trên TOAN_6_HK1.docx/HK2.docx): dòng tiêu đề
    (merge toàn bộ), dòng header ("STT", "Mức độ", ...), dòng đánh số cột thứ tự
    (1..10), rồi tới các dòng dữ liệu. Cột 0 = STT, cột 9 = Số câu — không dùng ở
    bước parse này (Số câu để trống, tính sau ở build_blueprint).
    """
    document = Document(str(path))
    table = document.tables[0]

    header_idx = next(
        i for i, row in enumerate(table.rows) if row.cells[0].text.strip() == "STT"
    )
    data_start = header_idx + 2  # bỏ qua dòng header + dòng đánh số cột (1..10)

    raw_rows = [_raw_row_texts(row)[1:9] for row in table.rows[data_start:]]
    return parse_matrix_rows(raw_rows)

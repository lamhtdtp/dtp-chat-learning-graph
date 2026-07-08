"""Parse ma trận đặc tả đề kiểm tra (.docx) thành dữ liệu có cấu trúc.

Ma trận là dữ liệu THIẾT KẾ đề (mức độ x mạch nội dung x tỉ lệ), khác hoàn toàn
SGK — không embed, không vào vector DB (xem skill data-ingestion). Đây là logic
deterministic, viết theo TDD (xem tests/ingestion/test_matrix_parser.py).
"""

from pathlib import Path
from typing import Literal

from docx import Document
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


class MatrixRow(BaseModel):
    muc_do: MucDo
    nang_luc_thanh_phan: str
    bieu_hien_nang_luc: str
    yeu_cau_can_dat: str
    mach_noi_dung: str
    don_vi_kien_thuc: str
    dang_thuc: str
    ti_le: float


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

    for row_idx, row in enumerate(rows):
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
            )
        )

    return records


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

    raw_rows = [
        [cell.text.strip() for cell in row.cells][1:9] for row in table.rows[data_start:]
    ]
    return parse_matrix_rows(raw_rows)

from typing import TypedDict

from app.exam.check import CauHoi


class ExamState(TypedDict, total=False):
    mach_noi_dung: str          # dùng để retrieve ngữ liệu SGK
    mon: str                    # giá trị `mon` trong Qdrant để lọc (vd "toan", "tieng_anh")
    khoi: str                   # giá trị `khoi` trong Qdrant (vd "lop_6")
    chi_tieu: dict[str, int]    # muc_do -> số câu cần (từ build_blueprint)
    de_thi: list[CauHoi]        # tích luỹ qua các vòng lặp
    so_lan_lap: int
    canh_bao: str | None        # đặt khi chạm trần mà chưa đủ

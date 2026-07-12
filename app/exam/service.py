"""Sinh đề đầu-cuối: nạp ma trận đã parse từ Postgres -> tính chỉ tiêu số câu
theo mức độ (deterministic) -> chạy graph sinh đề (exam_gen <-> check có vòng
lặp) -> trả đề + cảnh báo.

Đếm/phân bổ số câu là CODE (build_blueprint, largest-remainder), LLM chỉ soạn
nội dung câu hỏi. Khớp ma trận = đúng phân bố mức độ, kiểm bằng check_node
(xem full-system-spec mục 7, 9).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Blueprint, BlueprintCell, CurriculumTopic, Grade, Subject
from app.exam.blueprint import build_blueprint
from app.graph.exam_build import build_exam_graph

# Graph không có checkpointer (sinh đề là tác vụ 1 lần, không cần lịch sử) nên
# compile 1 lần dùng lại được, không cần Redis.
_EXAM_GRAPH = build_exam_graph()

# Tên hiển thị (Subject.name/Grade.name để tra blueprint) -> giá trị `mon`/`khoi`
# trong Qdrant (để exam_gen retrieve ngữ liệu đúng môn). Thêm môn = thêm 1 dòng.
_MON_QDRANT = {"Toán": "toan", "Tiếng Anh": "tieng_anh"}
_KHOI_QDRANT = {"Lớp 6": "lop_6"}


class BlueprintNotFound(Exception):
    """Chưa nạp ma trận cho (môn, khối, học kỳ) yêu cầu."""


async def _load_blueprint(
    session: AsyncSession, *, mon: str, khoi: str, hoc_ky: str
) -> Blueprint:
    subject = await session.scalar(select(Subject).filter_by(name=mon))
    grade = await session.scalar(select(Grade).filter_by(name=khoi))
    if subject is None or grade is None:
        raise BlueprintNotFound(f"Chưa có môn {mon!r} hoặc khối {khoi!r}")
    bp = await session.scalar(
        select(Blueprint).filter_by(
            subject_id=subject.id, grade_id=grade.id, semester=hoc_ky
        )
    )
    if bp is None:
        raise BlueprintNotFound(f"Chưa nạp ma trận cho {mon} {khoi} {hoc_ky}")
    return bp


def _ti_le_theo_muc_do(cells: list[BlueprintCell]) -> dict[str, float]:
    """Cộng tỉ lệ % theo mức độ, mỗi nhóm tỉ lệ (`nhom_ti_le`) chỉ tính một lần
    — cùng quy tắc `matrix_parser.tong_ti_le_theo_muc_do`, nhưng đọc từ DB."""
    seen: set[int] = set()
    totals: dict[str, float] = {}
    for c in cells:
        if c.nhom_ti_le in seen:
            continue
        seen.add(c.nhom_ti_le)
        totals[c.muc_do] = totals.get(c.muc_do, 0.0) + c.ti_le
    return totals


async def tinh_chi_tieu(
    session: AsyncSession,
    *,
    hoc_ky: str,
    tong_so_cau: int,
    mon: str = "Toán",
    khoi: str = "Lớp 6",
) -> tuple[Blueprint, dict[str, int], dict[str, float]]:
    """Nạp blueprint + tính chỉ tiêu số câu theo mức độ (deterministic). Dùng
    chung cho sinh đề (SGK) và gợi ý Itest (EPIC-10) để cùng một ma trận."""
    bp = await _load_blueprint(session, mon=mon, khoi=khoi, hoc_ky=hoc_ky)
    cells = list(
        await session.scalars(select(BlueprintCell).filter_by(blueprint_id=bp.id))
    )
    ti_le = _ti_le_theo_muc_do(cells)
    chi_tieu = build_blueprint(ti_le, tong_so_cau)
    return bp, chi_tieu, ti_le


async def sinh_de(
    session: AsyncSession,
    *,
    hoc_ky: str,
    tong_so_cau: int,
    mon: str = "Toán",
    khoi: str = "Lớp 6",
) -> dict:
    bp, chi_tieu, ti_le = await tinh_chi_tieu(
        session, hoc_ky=hoc_ky, tong_so_cau=tong_so_cau, mon=mon, khoi=khoi
    )
    cells = list(
        await session.scalars(select(BlueprintCell).filter_by(blueprint_id=bp.id))
    )

    # mạch nội dung phủ trong học kỳ (theo order_index) — dùng làm câu truy vấn
    # ngữ liệu SGK cho node sinh đề.
    topic_ids = {c.topic_id for c in cells}
    topics = list(
        await session.scalars(
            select(CurriculumTopic)
            .where(CurriculumTopic.id.in_(topic_ids))
            .order_by(CurriculumTopic.order_index)
        )
    )
    mach_list = list(dict.fromkeys(t.mach_noi_dung for t in topics))

    result = await _EXAM_GRAPH.ainvoke(
        {
            "mach_noi_dung": "; ".join(mach_list),
            # exam_gen retrieve theo môn/khối tương ứng (đa môn: Toán, Tiếng Anh…).
            "mon": _MON_QDRANT.get(mon, "toan"),
            "khoi": _KHOI_QDRANT.get(khoi, "lop_6"),
            "chi_tieu": chi_tieu,
            "de_thi": [],
            "so_lan_lap": 0,
        }
    )

    cau_hoi = [
        c.model_dump() if hasattr(c, "model_dump") else dict(c)
        for c in result.get("de_thi", [])
    ]
    return {
        "hoc_ky": hoc_ky,
        "tong_so_cau": tong_so_cau,
        "chi_tieu": chi_tieu,
        "ti_le_muc_do": ti_le,
        "mach_noi_dung": mach_list,
        "cau_hoi": cau_hoi,
        "canh_bao": result.get("canh_bao"),
        "so_lan_lap": result.get("so_lan_lap", 0),
    }

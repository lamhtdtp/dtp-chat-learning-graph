"""Gợi ý câu hỏi Itest theo blueprint (EPIC-10, US-23).

Với mỗi ô ma trận (topic × mức độ, cần N câu), match câu Itest ĐÃ MAP & ĐÃ DUYỆT
đúng ô đó, rank + dedupe rồi trả danh sách ứng viên + báo phần còn thiếu. Toàn
bộ là CODE deterministic — không giao LLM (cùng tư tưởng build_blueprint/check).
Câu chưa duyệt (cho_duyet/chua_map) KHÔNG xuất hiện để không lệch ma trận.
"""

from __future__ import annotations

import json

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BlueprintCell, ItestQuestion, ItestTopicMap


class SuggestCell(BaseModel):
    topic_id: int
    muc_do: str
    so_cau_can: int


class UngVien(BaseModel):
    itest_id: str
    noi_dung: str
    options: list[str] = []
    dap_an: str = ""      # đáp án đúng (để học sinh tự kiểm sau khi làm)
    loi_giai: str = ""    # lời giải nếu Itest có
    tag_goc: str


class CellSuggestion(BaseModel):
    topic_id: int
    muc_do: str
    so_cau_can: int
    ung_vien: list[UngVien]
    con_thieu: int  # >0 nghĩa là ngân hàng Itest thiếu câu cho ô này


def _rank_dedupe(rows: list[ItestQuestion]) -> list[ItestQuestion]:
    """Rank độ mới (synced_at giảm dần) + tie-break itest_id (tất định); dedupe
    theo content_hash và itest_id để không đề xuất 2 câu trùng."""
    ordered = sorted(rows, key=lambda q: (q.synced_at, q.itest_id), reverse=True)
    seen_hash: set[str] = set()
    seen_id: set[str] = set()
    out: list[ItestQuestion] = []
    for q in ordered:
        if q.itest_id in seen_id or q.content_hash in seen_hash:
            continue
        seen_id.add(q.itest_id)
        seen_hash.add(q.content_hash)
        out.append(q)
    return out


def _fmt_dap_an(raw: str | None) -> str:
    """Chuẩn hoá đáp án để hiển thị: Itest ngăn nhiều đáp án đúng bằng '#' -> đổi
    thành ', ' cho dễ đọc."""
    return ", ".join(p.strip() for p in (raw or "").split("#") if p.strip())


def _to_ung_vien(q: ItestQuestion) -> UngVien:
    options = json.loads(q.options_json) if q.options_json else []
    return UngVien(
        itest_id=q.itest_id, noi_dung=q.noi_dung, options=options,
        dap_an=_fmt_dap_an(q.dap_an), loi_giai=q.loi_giai or "", tag_goc=q.tag_goc,
    )


async def suggest_for_cells(
    session: AsyncSession, cells: list[SuggestCell]
) -> list[CellSuggestion]:
    """Gợi ý ứng viên Itest cho từng ô. Chỉ lấy câu có tag ĐÃ DUYỆT khớp
    (topic_id, muc_do) của ô."""
    result: list[CellSuggestion] = []
    for cell in cells:
        rows = list(await session.scalars(
            select(ItestQuestion)
            .join(ItestTopicMap, ItestTopicMap.itest_tag == ItestQuestion.tag_goc)
            .where(
                ItestTopicMap.status == "da_duyet",
                ItestTopicMap.topic_id == cell.topic_id,
                ItestTopicMap.muc_do == cell.muc_do,
            )
        ))
        ranked = _rank_dedupe(rows)
        result.append(CellSuggestion(
            topic_id=cell.topic_id,
            muc_do=cell.muc_do,
            so_cau_can=cell.so_cau_can,
            ung_vien=[_to_ung_vien(q) for q in ranked],
            con_thieu=max(0, cell.so_cau_can - len(ranked)),
        ))
    return result


def phan_bo(weights: dict, tong: int) -> dict:
    """Chia `tong` cho các khoá theo trọng số (largest-remainder) — tổng LUÔN
    khớp `tong`. Tổng quát hoá build_blueprint (không cần trọng số cộng thành 100)."""
    tong_w = sum(weights.values())
    if tong_w <= 0 or tong <= 0:
        return {k: 0 for k in weights}
    le = {k: w / tong_w * tong for k, w in weights.items()}
    nguyen = {k: int(v) for k, v in le.items()}
    con_thieu = tong - sum(nguyen.values())
    uu_tien = sorted(le, key=lambda k: le[k] - nguyen[k], reverse=True)
    for k in uu_tien[:con_thieu]:
        nguyen[k] += 1
    return nguyen


# Gợi ý câu Itest cho HỌC SINH trong chat KHÔNG dùng mirror/taxonomy nữa mà query
# i-Test trực tiếp thành bài trắc nghiệm tương tác — xem app/integrations/itest/
# quiz.py (port từ repo dtp-chat-learning). Module này chỉ còn suggest-theo-
# blueprint cho GIÁO VIÊN (US-23) + assemble (US-24).


async def build_suggest_cells(
    session: AsyncSession, blueprint_id: int, chi_tieu: dict[str, int]
) -> list[SuggestCell]:
    """Từ blueprint_cells + chỉ tiêu số câu theo mức độ, dựng danh sách ô
    (topic, muc_do, so_cau_can): phân bổ tổng câu mỗi mức độ cho các topic của
    mức đó theo tỉ lệ ô (deterministic, largest-remainder)."""
    cells = list(await session.scalars(
        select(BlueprintCell).where(BlueprintCell.blueprint_id == blueprint_id)
    ))
    out: list[SuggestCell] = []
    for muc_do, tong in chi_tieu.items():
        cua_muc = [c for c in cells if c.muc_do == muc_do]
        if not cua_muc or tong <= 0:
            continue
        # Gộp theo topic_id, trọng số = tổng ti_le các cell cùng topic của mức này.
        weights: dict[int, float] = {}
        for c in cua_muc:
            weights[c.topic_id] = weights.get(c.topic_id, 0.0) + c.ti_le
        phan = phan_bo(weights, tong)
        for topic_id, so_cau in phan.items():
            if so_cau > 0:
                out.append(SuggestCell(topic_id=topic_id, muc_do=muc_do, so_cau_can=so_cau))
    return out

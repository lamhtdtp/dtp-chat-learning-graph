"""Gợi ý câu hỏi Itest theo blueprint (EPIC-10, US-23).

Với mỗi ô ma trận (topic × mức độ, cần N câu), match câu Itest ĐÃ MAP & ĐÃ DUYỆT
đúng ô đó, rank + dedupe rồi trả danh sách ứng viên + báo phần còn thiếu. Toàn
bộ là CODE deterministic — không giao LLM (cùng tư tưởng build_blueprint/check).
Câu chưa duyệt (cho_duyet/chua_map) KHÔNG xuất hiện để không lệch ma trận.
"""

from __future__ import annotations

import json
import re
import unicodedata

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


def _to_ung_vien(q: ItestQuestion) -> UngVien:
    options = json.loads(q.options_json) if q.options_json else []
    return UngVien(itest_id=q.itest_id, noi_dung=q.noi_dung, options=options, tag_goc=q.tag_goc)


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


# ── Gợi ý bài tập/đề Itest trong CHAT cho học sinh ────────────────────────────
# Khác suggest-theo-blueprint (US-23, cần đã-duyệt để khớp ma trận): đây là gợi
# ý luyện tập nhẹ trong câu trả lời — match theo TỪ KHOÁ chủ đề với tên đề Itest
# (giống generate_quiz repo dtp-chat-learning), chạy trên MIRROR cục bộ nên nhanh
# và không phụ thuộc taxonomy đã duyệt.

# Từ bỏ qua khi so khớp (đã bỏ dấu): chức năng + từ chung của tên đề/câu hỏi.
_KW_STOP = set(
    "em muon hoc ve gi cho cua va cac mot duoc co voi khi tu nay nhung theo nhu thi minh "
    "bai tap lop toan kiem tra de thi mon thuong xuyen giua cuoi giai thich la nao sau day "
    "hay tinh tim hoi luyen".split()
)


def _ascii(s: object) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s or "").lower())
        if unicodedata.category(c) != "Mn"
    )


def _keywords(text: str | None) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", _ascii(text)) if len(w) >= 3 and w not in _KW_STOP]


class GoiYItest(BaseModel):
    bai_tap: list[UngVien]  # vài câu luyện tập cụ thể
    de: list[str]           # tên các đề Itest liên quan (tag_goc)


async def suggest_cho_hoc_sinh(
    session: AsyncSession, query: str, *, limit_bai: int = 3, limit_de: int = 3
) -> GoiYItest | None:
    """Gợi ý bài tập + đề Itest liên quan tới câu học sinh hỏi, dựa trên độ khớp
    từ khoá với TÊN ĐỀ (tag_goc) trên mirror. Không khớp -> None (không gợi ý
    lung tung). Tất định: xếp theo số từ khoá trùng, tie-break tên đề rồi itest_id."""
    kws = _keywords(query)
    if not kws:
        return None

    tags = list(await session.scalars(select(ItestQuestion.tag_goc).distinct()))
    scored = [(sum(1 for k in kws if k in _ascii(t)), t) for t in tags]
    khop = sorted([(s, t) for s, t in scored if s > 0], key=lambda x: (-x[0], x[1]))
    if not khop:
        return None

    top_tags = [t for _s, t in khop[:limit_de]]
    # Lấy bài tập theo thứ tự ĐỀ KHỚP TỐT NHẤT trước (không trộn theo recency, để
    # câu gợi ý đúng chủ đề học sinh hỏi), dedupe theo content_hash.
    bai_tap: list[UngVien] = []
    seen_hash: set[str] = set()
    for tag in top_tags:
        if len(bai_tap) >= limit_bai:
            break
        rows = list(await session.scalars(
            select(ItestQuestion)
            .where(ItestQuestion.tag_goc == tag)
            .order_by(ItestQuestion.itest_id)
        ))
        for q in rows:
            if len(bai_tap) >= limit_bai:
                break
            if q.content_hash in seen_hash:
                continue
            seen_hash.add(q.content_hash)
            bai_tap.append(_to_ung_vien(q))
    return GoiYItest(bai_tap=bai_tap, de=top_tags)


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

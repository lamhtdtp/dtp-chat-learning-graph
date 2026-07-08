"""Cắt markdown OCR của 1 trang SGK thành các chunk theo ranh giới ngữ nghĩa.

Cắt theo ranh giới mục/marker (heading, VÍ DỤ, LUYỆN TẬP, HOẠT ĐỘNG...), KHÔNG
cắt cứng theo số ký tự — cắt giữa một ví dụ/định lí sẽ làm hỏng retrieval (xem
skill data-ingestion). Mỗi chunk gắn đủ metadata để retriever filter theo
khối/chương và để trace nguồn.

Deterministic sau khi đã có markdown -> TDD được (tests/ingestion/test_chunking.py).
"""

import re
from typing import Literal

from pydantic import BaseModel

from app.ingestion.page_structure import PageStructure

LoaiNoiDung = Literal["ly_thuyet", "vi_du", "bai_tap"]

# Chunk ngắn hơn ngưỡng này (ký tự, tính phần nội dung) được gộp vào chunk trước
# để tránh chunk rác (vd 1 dòng chú thích hình lẻ loi).
_MIN_CHUNK_CHARS = 40

_HEADING_RE = re.compile(r"^\s*#{1,6}\s+\S")
# Dòng marker in đậm dạng "**VÍ DỤ 1**", "**LUYỆN TẬP 2**"...
_BOLD_MARKER_RE = re.compile(r"^\s*\*\*\s*(VÍ DỤ|LUYỆN TẬP|BÀI TẬP|HOẠT ĐỘNG|THỰC HÀNH|VẬN DỤNG)", re.IGNORECASE)
# Footer chân trang: "2 | Chương 1 - Số tự nhiên" và đường kẻ "---".
_FOOTER_RE = re.compile(r"^\s*\d+\s*\|\s*ch[uư]ơng", re.IGNORECASE)
_HR_RE = re.compile(r"^\s*-{3,}\s*$")

_BAI_TAP_KEYWORDS = ("LUYỆN TẬP", "BÀI TẬP", "HOẠT ĐỘNG", "THỰC HÀNH", "VẬN DỤNG")


class ChunkMetadata(BaseModel):
    mon: str
    khoi: str
    sach: str
    tap: int | None
    chuong_so: int | None
    chuong_ten: str | None
    bai_so: int | None
    bai_ten: str | None
    page_no: int
    nguon: str
    loai_noi_dung: LoaiNoiDung
    # topic_id (FK sang Postgres curriculum_topics) CỐ Ý chưa gắn ở đây: nối
    # nội dung SGK với taxonomy ma trận cần bước chuẩn hoá/đối chiếu thủ công
    # (rủi ro 13.4 trong full-system-spec) — không bịa topic_id chưa đáng tin.


class Chunk(BaseModel):
    content: str
    metadata: ChunkMetadata


def _is_boundary(line: str) -> bool:
    return bool(_HEADING_RE.match(line) or _BOLD_MARKER_RE.match(line))


def _classify(first_line: str) -> LoaiNoiDung:
    text = first_line.upper()
    if "VÍ DỤ" in text:
        return "vi_du"
    if any(kw in text for kw in _BAI_TAP_KEYWORDS):
        return "bai_tap"
    return "ly_thuyet"


def _strip_footer(markdown: str) -> list[str]:
    return [
        line
        for line in markdown.splitlines()
        if not _FOOTER_RE.match(line) and not _HR_RE.match(line)
    ]


def chunk_page(
    markdown: str,
    page: PageStructure,
    *,
    mon: str,
    khoi: str,
    sach: str,
    tap: int | None,
) -> list[Chunk]:
    lines = _strip_footer(markdown)

    # Gom lines thành segment: mỗi segment bắt đầu tại 1 dòng boundary (hoặc từ
    # đầu trang tới boundary đầu tiên). Giữ nguyên thứ tự.
    segments: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _is_boundary(line) and current and any(s.strip() for s in current):
            segments.append(current)
            current = [line]
        else:
            current.append(line)
    if any(s.strip() for s in current):
        segments.append(current)

    # Mỗi segment -> (content, loai_noi_dung), bỏ segment rỗng.
    typed: list[tuple[str, LoaiNoiDung]] = []
    for seg in segments:
        content = "\n".join(seg).strip()
        if not content:
            continue
        typed.append((content, _classify(seg[0])))

    # Gộp segment quá ngắn vào chunk trước (giữ loại của chunk trước).
    merged: list[tuple[str, LoaiNoiDung]] = []
    for content, kind in typed:
        if merged and len(content) < _MIN_CHUNK_CHARS:
            prev_content, prev_kind = merged[-1]
            merged[-1] = (prev_content + "\n" + content, prev_kind)
        else:
            merged.append((content, kind))

    nguon = f"Toán 6 – Cùng khám phá, Tập {tap}, tr.{page.page_no}"
    return [
        Chunk(
            content=content,
            metadata=ChunkMetadata(
                mon=mon,
                khoi=khoi,
                sach=sach,
                tap=tap,
                chuong_so=page.chuong_so,
                chuong_ten=page.chuong_ten,
                bai_so=page.bai_so,
                bai_ten=page.bai_ten,
                page_no=page.page_no,
                nguon=nguon,
                loai_noi_dung=kind,
            ),
        )
        for content, kind in merged
    ]

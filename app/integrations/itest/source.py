"""Nguồn câu hỏi Itest — READ-ONLY (EPIC-10, US-21).

`ItestSource` là giao diện cắm được: test dùng nguồn giả, prod dùng `DbItestSource`
đọc DB Itest ngoài (schema unit_test → unit_test_part → unit_test_part_questions →
question; subject='MATH', grade_id='G6' — xem repo dtp-chat-learning/backend/app/
quiz.py). KHÔNG có bất kỳ đường ghi nào chạm DB Itest: mọi truy cập đi qua
`_select()` chỉ chấp nhận câu lệnh SELECT (đọc), chặn ghi/sửa/xoá ngay ở tầng
adapter kể cả khi credential lỡ có quyền ghi.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.config import settings

# Giá trị thật trong DB Itest (xem quiz.py tham chiếu).
_SUBJECT_MATH = "MATH"
_GRADE_ID = "G6"

_QUESTIONS_SQL = """
    SELECT ut.id AS unit_test_id, ut.name AS tag_goc,
           q.id AS question_id, q.question_type, q.image,
           q.question_text, q.question_description, q.answers, q.correct_answers
    FROM unit_test ut
    JOIN unit_test_part utp ON utp.unit_test_id = ut.id
    JOIN unit_test_part_questions utpq ON utpq.unit_test_part_id = utp.id
    JOIN question q ON q.id = utpq.questions_id
    WHERE ut.deleted = 0 AND q.deleted = 0
      AND ut.subject = :sub AND ut.grade_id = :grd
    ORDER BY ut.id, utpq.sort_order
"""


def _clean(s: object) -> str:
    """Bỏ thẻ HTML + gọn khoảng trắng (giống quiz.py tham chiếu)."""
    t = re.sub(r"<[^>]+>", " ", str(s or ""))
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", t).strip()


def _split_options(raw: object) -> list[str]:
    """Lựa chọn ngăn nhau bằng '*' hoặc '#' (định dạng DB Itest)."""
    s = str(raw or "")
    for sep in ("*", "#", "\n", ";", "|"):
        parts = [p for p in (_clean(x) for x in s.split(sep)) if p]
        if len(parts) >= 2:
            return parts
    one = _clean(s)
    return [one] if one else []


class ItestRecord(BaseModel):
    """1 câu hỏi thô từ nguồn Itest (đã làm sạch, chưa map taxonomy)."""

    itest_id: str
    tag_goc: str  # tên đề (unit_test.name) — khoá ánh xạ taxonomy
    question_type: str = "MC"
    noi_dung: str
    options: list[str] = Field(default_factory=list)
    dap_an: str = ""
    loi_giai: str = ""
    image_url: str | None = None

    def content_hash(self) -> str:
        """Hash nội dung để sync idempotent: đổi hash -> cập nhật, cùng hash -> bỏ qua."""
        payload = json.dumps(
            {"q": self.noi_dung, "o": self.options, "a": self.dap_an,
             "t": self.question_type, "g": self.loi_giai},
            ensure_ascii=False, sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@runtime_checkable
class ItestSource(Protocol):
    async def fetch_questions(self) -> list[ItestRecord]: ...


class ReadOnlyViolation(Exception):
    """Chặn mọi câu lệnh không phải SELECT ở tầng adapter Itest."""


def _img_url(raw: object) -> str | None:
    s = _clean(raw)
    if not s:
        return None
    if s.startswith(("http://", "https://")):
        return s
    return settings.itest_cdn_base.rstrip("/") + "/" + s.lstrip("/")


def _row_to_record(row: dict) -> ItestRecord | None:
    stem = _clean(row.get("question_description")) or _clean(row.get("question_text"))
    options = _split_options(row.get("answers")) or _split_options(row.get("question_text"))
    if not stem:
        return None
    return ItestRecord(
        itest_id=str(row["question_id"]),
        tag_goc=_clean(row.get("tag_goc")) or f"unit_test:{row.get('unit_test_id')}",
        question_type=(row.get("question_type") or "MC").upper(),
        noi_dung=stem,
        options=options,
        dap_an=_clean(row.get("correct_answers")),
        image_url=_img_url(row.get("image")),
    )


class DbItestSource:
    """Đọc DB Itest ngoài qua engine CHỈ-ĐỌC riêng. Chỉ SELECT — không commit,
    không insert/update/delete. Engine tách biệt, không nằm trong transaction ghi
    nào của app (Nguyên tắc read-only tuyệt đối, Architecture §5)."""

    def __init__(self, database_url: str | None = None) -> None:
        self._url = database_url or settings.itest_database_url
        self._engine = None

    def _get_engine(self):
        if not self._url:
            raise RuntimeError("Chưa cấu hình ITEST_DATABASE_URL (DB Itest read-only)")
        if self._engine is None:
            from sqlalchemy import create_engine
            self._engine = create_engine(
                self._url, pool_pre_ping=True, pool_recycle=3600, pool_size=3,
            )
        return self._engine

    def _select(self, sql: str, params: dict) -> list[dict]:
        """CỬA DUY NHẤT tới DB Itest — chỉ nhận SELECT. Bất kỳ lệnh ghi -> raise."""
        if not sql.lstrip().upper().startswith("SELECT"):
            raise ReadOnlyViolation(f"Chỉ cho phép SELECT trên DB Itest, gặp: {sql[:40]!r}")
        from sqlalchemy import text
        with self._get_engine().connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return [dict(r) for r in rows]

    async def fetch_questions(self) -> list[ItestRecord]:
        import asyncio

        rows = await asyncio.to_thread(
            self._select, _QUESTIONS_SQL, {"sub": _SUBJECT_MATH, "grd": _GRADE_ID}
        )
        out: list[ItestRecord] = []
        for r in rows:
            rec = _row_to_record(r)
            if rec is not None:
                out.append(rec)
        return out

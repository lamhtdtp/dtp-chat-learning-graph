"""Lấy ĐỀ THẬT (unit_test) Toán lớp 6 từ DB i-Test → bài trắc nghiệm tương tác.

Port từ repo dtp-chat-learning/backend/app/quiz.py (giữ nguyên cách làm): query
DB i-Test **READ-ONLY** trực tiếp mỗi lần (không qua mirror), chọn đề khớp nhất
với chủ đề học sinh hỏi, parse mọi dạng câu (MC/MR/TF/FB/MG) và resolve đáp án.

Khác bản gốc: KHÔNG dùng LLM fallback (theo yêu cầu) — câu chọn-1 không xác định
được đáp án để answer=-1 (hiện nhưng không chấm). Chỉ SELECT, không ghi i-Test.
"""

from __future__ import annotations

import json
import re
import unicodedata

from pydantic import BaseModel

from app.config import settings

# ── Giá trị thật trong DB i-Test ──
_SUBJECT_MATH = "MATH"
_GRADE_ID = "G6"
_TEXT_KEYS = ("text", "content", "answer", "value", "label", "name", "title")
_CORRECT_FLAGS = ("is_correct", "isCorrect", "correct", "isAnswer", "is_answer")

# Từ bỏ qua khi khớp chủ đề ↔ tên đề (đã bỏ dấu).
_KW_STOP = set(
    "em muon hoc ve gi cho cua va cac mot duoc co voi khi tu nay nhung theo nhu thi minh "
    "bai tap lop toan kiem tra de thi mon thuong xuyen giua cuoi giai thich".split()
)

_engine = None


def _get_engine():
    """Engine CHỈ-ĐỌC tới DB i-Test (tách biệt, dùng lại qua pool)."""
    global _engine
    if not settings.itest_database_url:
        raise RuntimeError("Chưa cấu hình ITEST_DATABASE_URL (DB i-Test read-only)")
    if _engine is None:
        from sqlalchemy import create_engine
        _engine = create_engine(
            settings.itest_database_url, pool_pre_ping=True, pool_recycle=3600, pool_size=3,
        )
    return _engine


def _ascii(s: object) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower())
                   if unicodedata.category(c) != "Mn")


def _keywords(topic: str | None) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", _ascii(topic)) if len(w) >= 3 and w not in _KW_STOP]


def _clean(s: object) -> str:
    t = re.sub(r"<[^>]+>", " ", str(s or ""))
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", t).strip()


def _try_json(raw: object):
    if isinstance(raw, (list, dict)):
        return raw
    s = raw or ""
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        return json.loads(s.strip())
    except (json.JSONDecodeError, ValueError):
        return None


def _split_options(raw: object) -> tuple[list[str], int | None]:
    """(danh sách lựa chọn, chỉ số đáp án đúng nếu nhúng cờ). Hỗ trợ JSON (mảng
    chuỗi/object có is_correct) hoặc văn bản ngăn bằng '*' (định dạng i-Test)."""
    data = _try_json(raw)
    if isinstance(data, list):
        opts: list[str] = []
        correct_idx: int | None = None
        for i, item in enumerate(data):
            if isinstance(item, dict):
                txt = next((item[k] for k in _TEXT_KEYS if item.get(k) not in (None, "")), "")
                opts.append(_clean(txt))
                if any(str(item.get(f)).lower() in ("1", "true") for f in _CORRECT_FLAGS):
                    correct_idx = i
            else:
                opts.append(_clean(item))
        return opts, correct_idx
    s = str(raw or "")
    for sep in ("*", "\n", ";", "|"):
        parts = [p for p in (_clean(x) for x in s.split(sep)) if p]
        if len(parts) >= 2:
            return parts, None
    one = _clean(s)
    return ([one] if one else []), None


def _correct_texts(raw: object) -> list[str]:
    data = _try_json(raw)
    if isinstance(data, list):
        out = []
        for x in data:
            if isinstance(x, dict):
                out.append(_clean(next((x[k] for k in _TEXT_KEYS if x.get(k) not in (None, "")), "")))
            else:
                out.append(_clean(x))
        return [o for o in out if o]
    return [_clean(p) for p in str(raw or "").split("*") if _clean(p)]


def _norm(s: object) -> str:
    t = _clean(s).lower()
    for tok in ("\\,", "\\;", "\\:", "\\!", "\\ ", "\\quad", "\\qquad"):
        t = t.replace(tok, "")
    return re.sub(r"\s+", "", t).strip(". ")


def _resolve_answer(correct_raw: object, opts: list[str], embedded: int | None) -> int | None:
    if embedded is not None:
        return embedded
    c = _try_json(correct_raw)
    val = c[0] if isinstance(c, list) and c else (c if not isinstance(c, (list, dict)) else None)
    if val is None and isinstance(correct_raw, str):
        val = correct_raw.strip()
    if val in (None, ""):
        return None
    s = str(val).strip()
    if len(s) == 1 and s.upper() in "ABCDEFGH":
        idx = ord(s.upper()) - 65
        return idx if 0 <= idx < len(opts) else None
    if s.isdigit():
        n = int(s)
        if 0 <= n < len(opts):
            return n
        if 1 <= n <= len(opts):
            return n - 1
    for i, o in enumerate(opts):
        if _clean(o) == _clean(s):
            return i
    return None


def _stem(row: dict, *skip_fields: str) -> str:
    for f in ("question_description", "question_text", "parent_question_text"):
        if f in skip_fields:
            continue
        raw = row.get(f)
        if raw and "*" not in str(raw) and "#" not in str(raw):
            s = _clean(raw)
            if s:
                return s
    return ""


def _img_url(raw: object) -> str | None:
    s = _clean(raw)
    if not s:
        return None
    if s.startswith(("http://", "https://")):
        return s
    return settings.itest_cdn_base.rstrip("/") + "/" + s.lstrip("/")


def _to_quiz_question(row: dict) -> dict | None:
    opts_a, ci_a = _split_options(row.get("answers"))
    opts_q, ci_q = _split_options(row.get("question_text"))
    if len(opts_a) >= 2:
        opts, embedded, from_answers = opts_a, ci_a, True
    elif len(opts_q) >= 2:
        opts, embedded, from_answers = opts_q, ci_q, False
    else:
        return None
    opts = [o for o in opts if o]
    if len(opts) < 2:
        return None
    ans = embedded
    if ans is None:
        cors = {_norm(c) for c in _correct_texts(row.get("correct_answers"))}
        for i, o in enumerate(opts):
            if _norm(o) in cors:
                ans = i
                break
    if ans is None:
        ans = _resolve_answer(row.get("correct_answers"), opts, None)
    if ans is not None and not 0 <= ans < len(opts):
        ans = None
    opt_field = "answers" if from_answers else "question_text"
    # KHÔNG LLM: chưa xác định -> -1 (hiện nhưng không chấm).
    return {"type": "single", "q": _stem(row, opt_field) or "Chọn đáp án đúng:",
            "options": opts, "answer": ans if ans is not None else -1}


def _q_multi(row: dict) -> dict | None:
    opts = [o for o in (_clean(x) for x in str(row.get("answers") or "").split("#")) if o]
    if len(opts) < 2:
        return None
    cors = {_norm(c) for c in str(row.get("correct_answers") or "").split("#") if _clean(c)}
    answers = [i for i, o in enumerate(opts) if _norm(o) in cors]
    return {"type": "multi", "q": _stem(row, "answers") or "Chọn các đáp án đúng:",
            "options": opts, "answers": answers}


def _q_truefalse(row: dict) -> list[dict]:
    statements = [s for s in (_clean(x) for x in str(row.get("answers") or "").split("#")) if s]
    cors = [c.strip().upper() for c in str(row.get("correct_answers") or "").split("#")]
    out: list[dict] = []
    for i, st in enumerate(statements):
        c = cors[i] if i < len(cors) else ""
        a = 0 if c.startswith("T") else (1 if c.startswith("F") else -1)
        out.append({"type": "single", "q": st, "options": ["Đúng", "Sai"], "answer": a})
    return out


def _q_fill(row: dict) -> list[dict]:
    """FB*: điền vào chỗ trống. GỘP mọi chỗ trống của 1 câu thành 1 câu duy nhất
    (nhiều ô nhập) thay vì tách N câu lặp lại đề. Thay ký hiệu %s% trong đề bằng
    '[...]' để thấy vị trí chỗ trống (nhiều chỗ -> đánh số [1] [2]… theo thứ tự)."""
    qtext = _clean(row.get("question_text")) or _clean(row.get("question_description")) or "Điền vào chỗ trống:"
    blanks = [_clean(x) for x in str(row.get("correct_answers") or "").split("#") if _clean(x)]
    if not blanks:
        return []
    n_slot = qtext.count("%s%")
    if n_slot > 1:
        i = 0

        def _mark(_m):
            nonlocal i
            i += 1
            return f"[{i}]"
        qtext = re.sub(r"%s%", _mark, qtext)
    else:
        qtext = qtext.replace("%s%", "[...]")
    return [{"type": "fill", "q": qtext, "blanks": blanks}]


def _q_match(row: dict) -> list[dict]:
    parts = str(row.get("answers") or "").split("#")
    left = [c for c in (_clean(x) for x in parts[0].split("*")) if c and c.upper() != "NBSP"]
    pool = ([c for c in (_clean(x) for x in parts[1].split("*")) if c and c.upper() != "NBSP"]
            if len(parts) > 1 else [])
    cors = [_clean(x.split("*")[0]) for x in str(row.get("correct_answers") or "").split("#")]
    if not left or not pool:
        return []
    out: list[dict] = []
    for i, l in enumerate(left):
        cor = cors[i] if i < len(cors) else ""
        ans = next((j for j, r in enumerate(pool) if _norm(r) == _norm(cor)), -1)
        out.append({"type": "single", "q": f'Nối: "{l}" tương ứng với?', "options": pool, "answer": ans})
    return out


def _q_select(row: dict) -> list[dict]:
    """SL*: chọn đáp án cho TỪNG chỗ trống. answers = các chỗ ngăn '#', mỗi chỗ
    có lựa chọn ngăn '*'; correct_answers = đáp án đúng mỗi chỗ (ngăn '#'). Mỗi
    chỗ -> 1 câu chọn-1 (tránh lẫn '#' vào lựa chọn như trước)."""
    blanks = str(row.get("answers") or "").split("#")
    cors = [_clean(c) for c in str(row.get("correct_answers") or "").split("#")]
    stem = _stem(row, "answers") or "Chọn đáp án thích hợp:"
    multi = len(blanks) > 1
    out: list[dict] = []
    for i, blank in enumerate(blanks):
        opts = [o for o in (_clean(x) for x in blank.split("*")) if o]
        if len(opts) < 2:
            continue
        cor = cors[i] if i < len(cors) else ""
        ans = next((j for j, o in enumerate(opts) if _norm(o) == _norm(cor)), -1)
        out.append({"type": "single",
                    "q": f"{stem} — Chỗ {i + 1}" if multi else stem,
                    "options": opts, "answer": ans})
    return out


def _expand(row: dict) -> list[dict]:
    qt = (row.get("question_type") or "").upper()
    if qt.startswith("SL"):
        qs = _q_select(row)
    elif qt.startswith("TF"):
        qs = _q_truefalse(row)
    elif qt.startswith("MG"):
        qs = _q_match(row)
    elif qt.startswith("FB"):
        qs = _q_fill(row)
    elif qt.startswith("MR"):
        q = _q_multi(row)
        qs = [q] if q else []
    else:
        q = _to_quiz_question(row)
        qs = [q] if q else []
    img = _img_url(row.get("image"))
    if img:
        for q in qs:
            q["image"] = img
    return qs


_QUESTIONS_SQL = """
    SELECT q.name, q.question_type, q.image, q.question_text, q.parent_question_text,
           q.question_description, q.answers, q.correct_answers
    FROM unit_test_part utp
    JOIN unit_test_part_questions utpq ON utpq.unit_test_part_id = utp.id
    JOIN question q ON q.id = utpq.questions_id
    WHERE utp.unit_test_id = :id AND q.deleted = 0
    ORDER BY utp.id, utpq.sort_order
"""

_CANDIDATES_SQL = """
    SELECT ut.id, ut.name
    FROM unit_test ut
    WHERE ut.deleted = 0 AND ut.subject = :sub AND ut.grade_id = :grd
    ORDER BY ut.is_publish DESC, ut.created_date DESC
    LIMIT 80
"""


class QuizQuestionOut(BaseModel):
    type: str                       # single | multi | fill | match
    q: str
    options: list[str] = []
    answer: int | None = None       # single
    answers: list[int] = []         # multi
    blanks: list[str] = []          # fill
    image: str | None = None


class QuizData(BaseModel):
    id: int                         # unit_test.id (truy vết đúng đề i-Test)
    title: str
    questions: list[QuizQuestionOut]


def generate_quiz(topic: str | None = None, n: int | None = None) -> QuizData:
    """Chọn đề Toán lớp 6 KHỚP NHẤT chủ đề (ổn định, không random): xếp theo số
    từ khoá tên đề trùng, tie-break publish + mới nhất. Trả đề đầu tiên đọc được
    câu trắc nghiệm. n=None = tất cả câu. Raise ValueError nếu không tìm được."""
    from sqlalchemy import text

    engine = _get_engine()
    with engine.connect() as conn:
        candidates = [dict(r) for r in conn.execute(
            text(_CANDIDATES_SQL), {"sub": _SUBJECT_MATH, "grd": _GRADE_ID}).mappings()]
        if not candidates:
            raise ValueError("Không tìm thấy đề Toán lớp 6 (MATH · G6) trong hệ thống")

        kws = _keywords(topic)
        if kws:
            candidates = sorted(
                candidates, key=lambda c: -sum(1 for k in kws if k in _ascii(c["name"])))

        for cand in candidates:
            rows = [dict(r) for r in conn.execute(text(_QUESTIONS_SQL), {"id": cand["id"]}).mappings()]
            parsed: list[dict] = []
            for r in rows:
                parsed.extend(_expand(r))
            if n:
                parsed = parsed[:n]
            if parsed:
                return QuizData(
                    id=cand["id"],
                    title=_clean(cand["name"]) or "Đề trắc nghiệm Toán 6",
                    questions=[QuizQuestionOut(**q) for q in parsed],
                )

    raise ValueError("Các đề Toán lớp 6 gần đây không có câu trắc nghiệm đọc được")

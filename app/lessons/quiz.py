"""Sinh "Kiểm tra nhanh" cho 1 đơn vị kiến thức — trắc nghiệm bám MA TRẬN.

Nguyên tắc (khớp mockup: phần ④ KHÓA, "sinh theo ma trận, không nhập tay"):
- Lấy các yêu cầu cần đạt (blueprint_cells.topic_id == topic) + mức độ.
- Grounding trên NỘI DUNG đã biên soạn của chính đơn vị (khái niệm + ví dụ),
  không cần Qdrant — quiz chỉ kiểm tra đúng phần đã học.
- LLM chỉ soạn NỘI DUNG câu hỏi trắc nghiệm; số câu / phân bố mức độ do code
  quyết (deterministic), giống luồng sinh đề (app/exam).

Kết quả cache vào topic_content.quiz_json để mọi HS dùng lại, không sinh lại
mỗi lần (giống cache video theo khái niệm).
"""
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BlueprintCell, CurriculumTopic, TopicContent
from app.llm import gateway

_LV = {"de", "trung_binh", "kho"}
_LV_TEN = {"de": "dễ", "trung_binh": "trung bình", "kho": "khó"}
# Số câu mặc định cho 1 bài kiểm tra nhanh (ngắn, cuối bài).
_SO_CAU_MAC_DINH = 8


def _phan_bo_muc_do(cells: list[BlueprintCell], so_cau: int) -> dict[str, int]:
    """Phân bổ số câu theo mức độ dựa trên các yêu cầu cần đạt của đơn vị.

    Ưu tiên phủ đủ các mức xuất hiện trong ma trận (mỗi mức ≥ 1 câu), phần dư
    chia theo tần suất mức. Không có cell -> tỉ lệ 1/2 dễ, 1/4 trung bình, 1/4 khó
    (so_cau=8 -> 4 dễ + 2 trung bình + 2 khó); phần dư dồn vào 'dễ' cho bài ôn nhanh."""
    freq: dict[str, int] = {}
    for c in cells:
        md = c.muc_do if c.muc_do in _LV else "de"
        freq[md] = freq.get(md, 0) + 1
    if not freq:
        mac_dinh = {"de": so_cau - 2 * (so_cau // 4), "trung_binh": so_cau // 4, "kho": so_cau // 4}
        return {m: n for m, n in mac_dinh.items() if n > 0}

    muc = sorted(freq, key=lambda m: (-freq[m], m))
    out = {m: 1 for m in muc}  # mỗi mức ít nhất 1 câu
    con_lai = so_cau - len(out)
    i = 0
    while con_lai > 0:
        out[muc[i % len(muc)]] += 1
        con_lai -= 1
        i += 1
    # Nếu số mức > so_cau: cắt bớt mức hiếm nhất cho khớp tổng.
    while sum(out.values()) > so_cau and len(out) > 1:
        hiem = min(out, key=lambda m: (freq[m], -ord(m[0])))
        del out[hiem]
    return out


def _salvage_objects(text: str) -> list[dict]:
    """Vớt object {...} hoàn chỉnh khi JSON tổng bị cắt (cùng ý tưởng
    exam_gen._salvage_objects) — object quiz nhận diện qua khoá 'q'."""
    objs: list[dict] = []
    stack: list[int] = []
    in_str = esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            frag = text[stack.pop():i + 1]
            try:
                obj = json.loads(frag)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "q" in obj and "o" in obj:
                objs.append(obj)
    return objs


def _parse_quiz(raw: str) -> list[dict]:
    """Bóc + CHUẨN HOÁ danh sách câu trắc nghiệm hợp lệ. Bỏ câu hỏng thay vì sập.

    Câu hợp lệ: q (str), o (>=2 phương án str), a (index đúng trong o), lv thuộc
    {de,trung_binh,kho}. giai tuỳ chọn."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    try:
        data = json.loads(text)
        items = data.get("quiz", []) if isinstance(data, dict) else data
        if not isinstance(items, list):
            items = []
    except json.JSONDecodeError:
        items = _salvage_objects(text)

    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        q = str(it.get("q", "")).strip()
        opts = it.get("o")
        a = it.get("a")
        if not q or not isinstance(opts, list) or len(opts) < 2:
            continue
        opts = [str(o).strip() for o in opts if str(o).strip()]
        if len(opts) < 2 or not isinstance(a, int) or not (0 <= a < len(opts)):
            continue
        lv = it.get("lv") if it.get("lv") in _LV else "de"
        out.append({"q": q, "o": opts, "a": a, "lv": lv, "giai": str(it.get("giai", "")).strip()})
    return out


def _prompt(dv: str, mach: str, ycd: list[str], phan_bo: dict[str, int], noi_dung: str) -> str:
    yeu_cau = ", ".join(f"{so} câu mức {_LV_TEN[md]}" for md, so in phan_bo.items())
    ycd_text = "\n".join(f"- {y}" for y in ycd) if ycd else "(bám nội dung bài học dưới đây)"
    return (
        "Bạn là giáo viên Toán lớp 6 soạn BÀI KIỂM TRA NHANH (trắc nghiệm 1 đáp án đúng) "
        f'cho đơn vị kiến thức "{dv}" thuộc mạch "{mach}".\n\n'
        "YÊU CẦU CẦN ĐẠT (bám sát, mỗi câu kiểm tra một ý):\n"
        f"{ycd_text}\n\n"
        "NỘI DUNG BÀI HỌC (chỉ hỏi trong phạm vi này, KHÔNG bịa ngoài):\n"
        f"{noi_dung or '(chưa có — soạn theo yêu cầu cần đạt, đúng chuẩn chương trình)'}\n\n"
        f"CẦN SOẠN: {yeu_cau}. Mỗi câu có ĐÚNG 4 phương án, một đáp án đúng, và 3 phương án "
        "nhiễu hợp lý (phản ánh lỗi sai thường gặp). Trả về JSON THUẦN:\n"
        '{"quiz": [{"q": "đề bài", "o": ["A","B","C","D"], "a": <chỉ số 0-3 của đáp án đúng>, '
        '"lv": "de|trung_binh|kho", "giai": "giải thích ngắn"}]}'
    )


async def _yeu_cau_can_dat(session: AsyncSession, topic: CurriculumTopic) -> tuple[list[str], list[BlueprintCell]]:
    """Các yêu cầu cần đạt + cells của MỌI đơn vị trùng tên (mục lục đã khử trùng
    nên 1 đơn vị ứng nhiều topic_id) trong cùng môn/khối."""
    twins = list(await session.scalars(
        select(CurriculumTopic).filter_by(
            subject_id=topic.subject_id, grade_id=topic.grade_id,
            mach_noi_dung=topic.mach_noi_dung, don_vi_kien_thuc=topic.don_vi_kien_thuc,
        )
    ))
    ids = [t.id for t in twins] or [topic.id]
    cells = list(await session.scalars(
        select(BlueprintCell).where(BlueprintCell.topic_id.in_(ids))
    ))
    ycd = list(dict.fromkeys(c.yeu_cau_can_dat for c in cells if c.yeu_cau_can_dat))
    return ycd, cells


def _grounding_text(content: TopicContent | None) -> str:
    if content is None:
        return ""
    parts = [content.khai_niem or ""]
    try:
        for e in json.loads(content.vi_du_json or "[]"):
            parts.append(f"Ví dụ: {e.get('de','')} — {e.get('giai','')}")
    except json.JSONDecodeError:
        pass
    return "\n".join(p for p in parts if p.strip())


async def generate_quiz(session: AsyncSession, topic_id: int, *, so_cau: int | None = None) -> list[dict]:
    """Sinh danh sách câu trắc nghiệm cho 1 đơn vị. Trả [] nếu không có topic.

    KHÔNG tự lưu — caller quyết định cache vào topic_content."""
    topic = await session.get(CurriculumTopic, topic_id)
    if topic is None:
        return []
    so_cau = so_cau or _SO_CAU_MAC_DINH
    ycd, cells = await _yeu_cau_can_dat(session, topic)
    phan_bo = _phan_bo_muc_do(cells, so_cau)
    content = await session.scalar(select(TopicContent).filter_by(topic_id=topic_id))
    messages = [{"role": "user", "content": _prompt(
        topic.don_vi_kien_thuc, topic.mach_noi_dung, ycd, phan_bo, _grounding_text(content),
    )}]
    raw = await gateway.complete(task="quiz_gen", messages=messages, max_tokens=4096)
    return _parse_quiz(raw)

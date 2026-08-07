"""AI nạp nháp nội dung bài học cho CMS (chuyên gia rà soát trước khi duyệt).

Sinh phần ① Khái niệm (HTML thuần, ngắn gọn đúng chuẩn chương trình) + ③ vài ví
dụ có lời giải, bám tên đơn vị + mạch + yêu cầu cần đạt (nếu có) + tư liệu nguồn
chuyên gia dán vào. KHÔNG tự lưu — trả nháp để chuyên gia chỉnh rồi PUT.
"""
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BlueprintCell, CurriculumTopic
from app.llm import gateway


def _prompt(dv: str, mach: str, ycd: list[str], nguon: str) -> str:
    ycd_text = "\n".join(f"- {y}" for y in ycd) if ycd else "(theo chuẩn chương trình Toán 6)"
    return (
        f'Soạn nội dung dạy học cho đơn vị kiến thức "{dv}" (mạch "{mach}"), Toán lớp 6, '
        "đúng chuẩn Chương trình GDPT 2018, ngắn gọn, dễ hiểu với học sinh lớp 6.\n\n"
        f"YÊU CẦU CẦN ĐẠT:\n{ycd_text}\n\n"
        f"TƯ LIỆU NGUỒN (nếu có, ưu tiên bám):\n{nguon or '(không có — tự soạn theo chuẩn)'}\n\n"
        "Trả JSON THUẦN:\n"
        '{"khai_niem": "<HTML: vài thẻ <p>, có thể <b>/<blockquote>, KHÔNG tiêu đề>", '
        '"vi_du": [{"de": "đề bài", "giai": "lời giải từng bước (HTML ngắn)"}]}\n'
        "Soạn 2–3 ví dụ từ dễ đến vận dụng."
    )


def _parse(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"khai_niem": "", "vi_du": []}
    if not isinstance(data, dict):
        return {"khai_niem": "", "vi_du": []}
    khai_niem = str(data.get("khai_niem", "")).strip()
    vi_du = []
    for e in data.get("vi_du", []) if isinstance(data.get("vi_du"), list) else []:
        if isinstance(e, dict) and str(e.get("de", "")).strip():
            vi_du.append({"de": str(e["de"]).strip(), "giai": str(e.get("giai", "")).strip()})
    return {"khai_niem": khai_niem, "vi_du": vi_du}


async def ingest_draft(session: AsyncSession, topic_id: int, *, nguon: str = "") -> dict:
    """Trả {khai_niem, vi_du} nháp. {} rỗng nếu không có topic."""
    topic = await session.get(CurriculumTopic, topic_id)
    if topic is None:
        return {"khai_niem": "", "vi_du": []}
    twins = list(await session.scalars(
        select(CurriculumTopic).filter_by(
            subject_id=topic.subject_id, grade_id=topic.grade_id,
            mach_noi_dung=topic.mach_noi_dung, don_vi_kien_thuc=topic.don_vi_kien_thuc,
        )
    ))
    ids = [t.id for t in twins] or [topic.id]
    cells = list(await session.scalars(select(BlueprintCell).where(BlueprintCell.topic_id.in_(ids))))
    ycd = list(dict.fromkeys(c.yeu_cau_can_dat for c in cells if c.yeu_cau_can_dat))
    messages = [{"role": "user", "content": _prompt(topic.don_vi_kien_thuc, topic.mach_noi_dung, ycd, nguon)}]
    raw = await gateway.complete(task="lesson_ingest", messages=messages, max_tokens=4096)
    return _parse(raw)

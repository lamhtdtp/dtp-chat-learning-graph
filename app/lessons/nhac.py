"""Sinh LỜI NHẮC CHỦ ĐỘNG cho 1 đơn vị kiến thức (lát 4, phương án D).

Trợ lý không chờ được hỏi: học sinh đọc xong phần khái niệm thì nó hỏi lại một
câu kiểm tra hiểu ngay tại chỗ. Nhóm cần nhất chính là nhóm đọc lướt không hiểu
mà cũng không biết mình cần hỏi gì.

QUAN TRỌNG — CHI PHÍ: sinh MỘT LẦN lúc biên soạn rồi cache vào
`topic_content.nhac_json`, y như `quiz_json`. Lúc học sinh đọc bài thì lời nhắc
lấy từ cache, KHÔNG gọi LLM, KHÔNG trừ vào hạn mức 20 lượt/ngày. Nếu để sinh
online thì mỗi lần cuộn qua khái niệm là một lượt, một buổi học đốt sạch hạn mức
mà học sinh chưa hỏi câu nào.

Học sinh muốn đào sâu -> hỏi tiếp trong chính thẻ, lúc đó mới tính lượt.
"""
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CurriculumTopic, TopicContent
from app.llm import gateway, jsonfix

# Mốc trong bài mà trợ lý được phép lên tiếng. Cố ý CHỈ có một: mỗi mốc là một
# lần cắt ngang mạch đọc, thêm mốc là thêm lý do để học sinh bấm "Tắt gợi ý".
_MOC = {"khai_niem"}
_SO_NHAC = 1


def _parse(raw: str) -> list[dict]:
    """Bóc + chuẩn hoá lời nhắc. Bỏ mục hỏng thay vì sập — nhắc là tính năng phụ,
    hỏng thì im lặng không nhắc chứ không được làm chết trang bài học."""
    data = jsonfix.boc_json(raw)
    items = (data.get("nhac", []) if isinstance(data, dict) else data) if data is not None else []
    if not isinstance(items, list):
        return []

    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        hoi = str(it.get("hoi", "")).strip()
        dap = it.get("dap")
        if not hoi or not isinstance(dap, list):
            continue
        dap = [str(d).strip() for d in dap if str(d).strip()][:4]
        if len(dap) < 2:
            continue
        dung = it.get("dung")
        # Không biết đáp án nào đúng thì lời nhắc thành vô nghĩa: học sinh bấm
        # chọn mà không được biết mình đúng hay sai. Bỏ luôn mục đó.
        if not isinstance(dung, int) or not (0 <= dung < len(dap)):
            continue
        moc = it.get("moc") if it.get("moc") in _MOC else "khai_niem"
        out.append({"moc": moc, "hoi": hoi, "dap": dap, "dung": dung,
                    "giai": str(it.get("giai", "")).strip()})
    return out[:_SO_NHAC]


def _prompt(dv: str, mach: str, khai_niem: str) -> str:
    return (
        "Bạn là gia sư Toán lớp 6 đang ngồi cạnh một học sinh vừa đọc xong phần "
        f'KHÁI NIỆM của bài "{dv}" (mạch "{mach}").\n\n'
        "NỘI DUNG EM ẤY VỪA ĐỌC:\n"
        f"{khai_niem}\n\n"
        "Hãy soạn ĐÚNG MỘT câu hỏi ngắn để kiểm tra em ấy có thực sự hiểu hay chỉ "
        "đọc lướt. Yêu cầu:\n"
        "- Trả lời được trong đầu, KHÔNG cần giấy nháp, KHÔNG cần tính toán dài.\n"
        "- Nhắm đúng chỗ học sinh hay nhầm ở phần khái niệm này.\n"
        "- Cho 2-3 phương án ngắn gọn để em ấy bấm chọn.\n"
        "- Giọng thân thiện, khích lệ, xưng 'mình' với 'bạn'.\n"
        "- Phần \"giai\" phải TRUNG TÍNH: đi thẳng vào lý do, KHÔNG mở đầu bằng lời "
        "khen hay chê ('Chính xác!', 'Đúng rồi', 'Sai rồi'…). Cùng một câu đó được "
        "hiện cho cả bạn trả lời đúng lẫn bạn trả lời sai, nên khen sẵn trong đó là "
        "mâu thuẫn với bạn vừa chọn nhầm.\n\n"
        "Trả về JSON THUẦN:\n"
        '{"nhac": [{"moc": "khai_niem", "hoi": "câu hỏi", "dap": ["phương án 1", "phương án 2"], '
        '"dung": <chỉ số 0-based của phương án ĐÚNG trong "dap">, '
        '"giai": "giải thích ngắn vì sao đáp án đó đúng"}]}'
    )


async def generate_nhac(session: AsyncSession, topic_id: int) -> list[dict]:
    """Sinh lời nhắc cho 1 đơn vị. Trả [] nếu chưa có nội dung khái niệm.

    KHÔNG tự lưu — caller quyết định cache vào topic_content."""
    topic = await session.get(CurriculumTopic, topic_id)
    if topic is None:
        return []
    content = await session.scalar(select(TopicContent).filter_by(topic_id=topic_id))
    khai_niem = (content.khai_niem or "").strip() if content else ""
    # Chưa soạn khái niệm thì không có gì để kiểm tra hiểu — đừng gọi LLM cho vui.
    if not khai_niem:
        return []
    messages = [{"role": "user", "content": _prompt(
        topic.don_vi_kien_thuc, topic.mach_noi_dung, khai_niem)}]
    # Rộng tay như quiz_gen dù nội dung cần trả về rất ngắn: tầng mạnh là model
    # reasoning, token SUY LUẬN ăn chung ngân sách với token trả lời. Đặt 2048
    # thì JSON bị cắt cụt ngay giữa mảng "dap" — lúc được lúc không, và hỏng thì
    # im lặng ra [] chứ không có lỗi nào để lần.
    raw = await gateway.complete(task="quiz_gen", messages=messages, max_tokens=16384)
    return _parse(raw)


def doc_nhac(content: TopicContent | None) -> list[dict]:
    """Đọc lời nhắc đã cache. JSON hỏng -> [] (không nhắc) thay vì ném lỗi ra
    giữa đường phục vụ bài học."""
    if content is None:
        return []
    try:
        items = json.loads(content.nhac_json or "[]")
    except json.JSONDecodeError:
        return []
    return items if isinstance(items, list) else []

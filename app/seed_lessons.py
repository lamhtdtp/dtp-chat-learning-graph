"""Seed 1 bài học mẫu (Số nguyên tố) vào TopicContent để P1 có nội dung thật xem
thử. Idempotent. Nội dung thật sẽ do chuyên gia biên soạn qua CMS (P4).

Dùng:  python -m app.seed_lessons
"""
import asyncio
import json

from sqlalchemy import select

from app.db.models import CurriculumTopic, TopicContent
from app.db.session import async_session_factory

_KHAI_NIEM = (
    "<p><b>Số nguyên tố</b> là số tự nhiên lớn hơn 1, chỉ có <b>đúng hai</b> ước "
    "là 1 và chính nó.</p><p><b>Hợp số</b> là số tự nhiên lớn hơn 1 và có <b>nhiều "
    "hơn hai</b> ước.</p><blockquote>Lưu ý: số 0 và 1 không phải số nguyên tố, cũng "
    "không phải hợp số.</blockquote>"
)
_MINH_HOA = [
    {"type": "video", "source": "ai", "url": None,
     "caption": "Video minh họa (AI tự sinh) — cách kiểm tra một số có phải số nguyên tố."},
]
_VI_DU = [
    {"de": "Số 7 là số nguyên tố hay hợp số?",
     "giai": "7 chỉ có hai ước là 1 và 7 → <b>7 là số nguyên tố</b>."},
    {"de": "Xét số 12.",
     "giai": "12 có các ước 1, 2, 3, 4, 6, 12 (nhiều hơn hai ước) → <b>12 là hợp số</b>."},
]
_DAY = {
    "muc_tieu": "HS nhận biết số nguyên tố, hợp số; giải thích vì sao 0 và 1 không thuộc hai loại này.",
    "thoi_luong": "1 tiết · ~45 phút",
    "luu_y": "Lỗi thường gặp: nhầm số 1 là số nguyên tố, hoặc tưởng mọi số chẵn đều là hợp số (quên số 2).",
}


async def _main() -> None:
    async with async_session_factory() as s:
        topic = await s.scalar(
            select(CurriculumTopic).where(CurriculumTopic.don_vi_kien_thuc.ilike("%số nguyên tố%"))
            .order_by(CurriculumTopic.id)
        )
        if topic is None:
            print("Không tìm thấy đơn vị chứa 'số nguyên tố' — chạy load_matrix_cli trước.")
            return
        c = await s.scalar(select(TopicContent).filter_by(topic_id=topic.id))
        if c is None:
            c = TopicContent(topic_id=topic.id)
            s.add(c)
        c.khai_niem = _KHAI_NIEM
        c.minh_hoa_json = json.dumps(_MINH_HOA, ensure_ascii=False)
        c.vi_du_json = json.dumps(_VI_DU, ensure_ascii=False)
        c.day_json = json.dumps(_DAY, ensure_ascii=False)
        c.nguon = "Biên soạn mẫu (seed)"
        c.trang_thai = "published"
        await s.commit()
        print(f"Đã seed bài học cho topic {topic.id}: {topic.don_vi_kien_thuc[:60]}")


if __name__ == "__main__":
    asyncio.run(_main())

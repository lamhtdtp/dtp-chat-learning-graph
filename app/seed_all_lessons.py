"""Nạp NHÁP nội dung bài học hàng loạt bằng AI cho các đơn vị CHƯA có nội dung.

    python -m app.seed_all_lessons [--publish] [--mon "Toán"] [--khoi "Lớp 6"]

Với mỗi đơn vị chưa có TopicContent: gọi AI soạn Khái niệm + Ví dụ
(app/lessons/ingest) và sinh Kiểm tra nhanh (app/lessons/quiz), lưu ở trạng thái
'draft' (mặc định) để chuyên gia duyệt — hoặc 'published' nếu truyền --publish.

Idempotent: BỎ QUA đơn vị đã có nội dung (không ghi đè bản đã biên soạn/đã xuất
bản, không tốn LLM lại). Lỗi 1 đơn vị -> bỏ qua, tiếp tục các đơn vị khác.

LƯU Ý: minh hoạ (video/ảnh) KHÔNG sinh ở đây — cần pipeline video hoặc chuyên gia
upload. Ma trận đã xoá khi reseed catalog nên nội dung bám tên đơn vị + chuẩn
chung, chưa bám "yêu cầu cần đạt".
"""
import argparse
import asyncio
import json

from sqlalchemy import select

from app.db.models import CurriculumTopic, Grade, Subject, TopicContent
from app.db.session import async_session_factory
from app.lessons import ingest as ingest_svc
from app.lessons import quiz as quiz_svc
from app.llm.gateway import LLMUnavailable


async def seed(*, mon: str, khoi: str, publish: bool) -> None:
    trang_thai = "published" if publish else "draft"
    async with async_session_factory() as session:
        subject = await session.scalar(select(Subject).filter_by(name=mon))
        grade = await session.scalar(select(Grade).filter_by(name=khoi))
        if subject is None or grade is None:
            print(f"✗ Chưa có môn {mon!r} / khối {khoi!r}. Chạy `python -m app.seed_curriculum` trước.")
            return

        topics = list(await session.scalars(
            select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id)
            .order_by(CurriculumTopic.order_index)
        ))
        have = set(await session.scalars(select(TopicContent.topic_id)))
        todo = [t for t in topics if t.id not in have]
        print(f"Tổng {len(topics)} đơn vị · đã có nội dung {len(have)} · cần soạn {len(todo)} (trạng thái: {trang_thai})")

        ok = fail = 0
        for i, t in enumerate(todo, 1):
            label = f"[{i}/{len(todo)}] {t.don_vi_kien_thuc[:52]}"
            try:
                draft = await ingest_svc.ingest_draft(session, t.id)
                try:
                    quiz = await quiz_svc.generate_quiz(session, t.id)
                except LLMUnavailable:
                    quiz = []
                session.add(TopicContent(
                    topic_id=t.id,
                    khai_niem=draft.get("khai_niem", ""),
                    minh_hoa_json="[]",
                    vi_du_json=json.dumps(draft.get("vi_du", []), ensure_ascii=False),
                    quiz_json=json.dumps(quiz, ensure_ascii=False),
                    nguon="AI soạn nháp (app.seed_all_lessons)",
                    trang_thai=trang_thai,
                ))
                await session.commit()
                ok += 1
                print(f"  ✓ {label} — khái niệm {'có' if draft.get('khai_niem') else 'trống'}, "
                      f"{len(draft.get('vi_du', []))} ví dụ, {len(quiz)} câu quiz")
            except LLMUnavailable:
                await session.rollback()
                fail += 1
                print(f"  ✗ {label} — AI quá tải, bỏ qua")
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                fail += 1
                print(f"  ✗ {label} — lỗi: {exc}")

        print(f"\nXong: {ok} đơn vị đã soạn, {fail} lỗi/bỏ qua. Trạng thái = {trang_thai}"
              + ("" if publish else " (vào CMS duyệt & xuất bản)."))


def main() -> None:
    ap = argparse.ArgumentParser(description="Nạp nháp nội dung bài học hàng loạt bằng AI")
    ap.add_argument("--mon", default="Toán")
    ap.add_argument("--khoi", default="Lớp 6")
    ap.add_argument("--publish", action="store_true", help="Xuất bản luôn (mặc định: draft)")
    args = ap.parse_args()
    asyncio.run(seed(mon=args.mon, khoi=args.khoi, publish=args.publish))


if __name__ == "__main__":
    main()

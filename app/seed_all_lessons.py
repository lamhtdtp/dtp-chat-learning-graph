"""Nạp NHÁP nội dung bài học hàng loạt bằng AI.

    python -m app.seed_all_lessons [--publish] [--mon "Toán"] [--khoi "Lớp 6"]
    python -m app.seed_all_lessons --force            # SOẠN LẠI cả đơn vị đã có

Với mỗi đơn vị: gọi AI soạn Khái niệm + Ví dụ bám ngữ liệu SGK
(app/lessons/ingest) và sinh Kiểm tra nhanh (app/lessons/quiz), lưu ở trạng thái
'draft' (mặc định) để chuyên gia duyệt — hoặc 'published' nếu truyền --publish.

Mặc định IDEMPOTENT: bỏ qua đơn vị đã có nội dung (không ghi đè bản đã biên
soạn/đã xuất bản, không tốn LLM lại). Lỗi 1 đơn vị -> bỏ qua, tiếp tục đơn vị khác.

--force GHI ĐÈ nội dung đã có — dùng khi cần soạn lại cả bộ sau khi đổi cách sinh
(vd nối grounding SGK, đổi số câu kiểm tra nhanh). Ghi đè khái niệm/ví dụ/quiz
và XOÁ phần chỉnh tay của chuyên gia, nên phải truyền cờ một cách có chủ đích.
GIỮ LẠI: minh hoạ đã có (ảnh/video chuyên gia upload lẫn AI đã sinh) và trạng
thái xuất bản — hai thứ tốn công/tốn tiền nhất, không đáng mất khi soạn lại chữ.
Thêm --publish thì mới đổi trạng thái đơn vị cũ sang 'published'.

--media sinh luôn minh hoạ: ảnh gọi model sinh ảnh NGAY (ghi vào storage), video
ngắn chỉ ĐẶT HÀNG job rồi worker queue 'video' dựng sau. Media THÊM vào phần đã
có, khử trùng theo url/concept_key nên chạy lại không nhân bản. Tốn thêm ~3
request mỗi đơn vị (1 đề xuất + 2 ảnh) — cộng với 2 request soạn bài + quiz.
Không có --media thì hành vi như cũ: chỉ soạn chữ.
"""
import argparse
import asyncio
import json

from sqlalchemy import select

from app.db.models import CurriculumTopic, Grade, Subject, TopicContent
from app.db.session import async_session_factory
from app.lessons import ingest as ingest_svc
from app.lessons import media as media_svc
from app.lessons import quiz as quiz_svc
from app.llm.gateway import LLMUnavailable


async def _sinh_media(session, topic, draft, cu_minh_hoa: list[dict]) -> tuple[list[dict], list[str]]:
    """Ảnh (sinh ngay) + video ngắn (đặt hàng job) cho 1 đơn vị.

    THÊM vào minh hoạ đang có, khử trùng theo url/concept_key — chạy lại script
    nhiều lần không nhân bản, và media chuyên gia tự thêm không bị mất.
    """
    them, loi = await media_svc.generate_images(topic.id, draft["anh"])
    vid, loi_vid = await media_svc.request_video(
        session, topic, draft["video"], mon=draft["mon"] or "toan")
    if vid:
        them.append(vid)
    da_co = {m.get("url") or m.get("concept_key") or "" for m in cu_minh_hoa}
    moi = [m for m in them if (m.get("url") or m.get("concept_key") or "") not in da_co]
    return cu_minh_hoa + moi, loi + loi_vid


async def seed(*, mon: str, khoi: str, publish: bool, force: bool, media: bool) -> None:
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
        # Chỉ đếm/tra nội dung của ĐÚNG môn+khối đang xử lý — bảng topic_content
        # chứa cả môn khác, lấy hết thì con số in ra sai.
        ids = {t.id for t in topics}
        cu = {c.topic_id: c for c in await session.scalars(
            select(TopicContent).where(TopicContent.topic_id.in_(ids or {0})))}
        todo = topics if force else [t for t in topics if t.id not in cu]
        ghi_de = sum(1 for t in todo if t.id in cu)
        print(f"Tổng {len(topics)} đơn vị · đã có nội dung {len(cu)} · sẽ soạn {len(todo)} "
              f"(trạng thái đơn vị mới: {trang_thai})")
        if ghi_de:
            print(f"⚠️  --force: GHI ĐÈ khái niệm/ví dụ/quiz của {ghi_de} đơn vị đã có "
                  "— mất phần chuyên gia chỉnh tay. Giữ lại minh hoạ"
                  + (" và xuất bản luôn." if publish else " + trạng thái xuất bản hiện tại."))

        ok = fail = 0
        for i, t in enumerate(todo, 1):
            label = f"[{i}/{len(todo)}] {t.don_vi_kien_thuc[:52]}"
            try:
                draft = await ingest_svc.ingest_draft(session, t.id)
                try:
                    quiz = await quiz_svc.generate_quiz(session, t.id)
                except LLMUnavailable:
                    quiz = []
                c = cu.get(t.id)
                if c is None:
                    c = TopicContent(topic_id=t.id, minh_hoa_json="[]", trang_thai=trang_thai)
                    session.add(c)
                elif publish:
                    c.trang_thai = "published"   # --publish là yêu cầu tường minh
                c.khai_niem = draft.get("khai_niem", "")
                c.vi_du_json = json.dumps(draft.get("vi_du", []), ensure_ascii=False)
                c.quiz_json = json.dumps(quiz, ensure_ascii=False)
                # Cờ AI là cột riêng — KHÔNG nhét chuỗi đánh dấu vào `nguon` nữa,
                # ô đó dành cho tư liệu chuyên gia dán vào.
                c.ai_soan = True
                loi_media: list[str] = []
                if media:
                    mh, loi_media = await _sinh_media(
                        session, t, draft, json.loads(c.minh_hoa_json or "[]"))
                    c.minh_hoa_json = json.dumps(mh, ensure_ascii=False)
                await session.commit()
                for m_ in loi_media:
                    print(f"    ⚠️  {m_}")
                ok += 1
                print(f"  ✓ {label} — khái niệm {'có' if draft.get('khai_niem') else 'trống'}, "
                      f"{len(draft.get('vi_du', []))} ví dụ, {len(quiz)} câu quiz"
                      + (" · bám SGK" if not draft.get("thieu_sgk") else " · ⚠️ KHÔNG bám SGK"))
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
    ap.add_argument("--force", action="store_true",
                    help="Soạn LẠI cả đơn vị đã có nội dung (ghi đè chữ, giữ minh hoạ)")
    ap.add_argument("--media", action="store_true",
                    help="Sinh luôn ảnh minh hoạ + đặt hàng video ngắn (tốn ~3 request/đơn vị)")
    args = ap.parse_args()
    asyncio.run(seed(mon=args.mon, khoi=args.khoi, publish=args.publish,
                     force=args.force, media=args.media))


if __name__ == "__main__":
    main()

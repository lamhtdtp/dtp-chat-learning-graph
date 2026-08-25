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

--phan soạn thêm 4 phần mà luồng chính KHÔNG sinh: Khởi động, Hoạt động,
Luyện tập – Vận dụng, Bài tập. Không có cờ này thì mỗi đơn vị chỉ ra 2/7 mục
(Kiến thức trọng tâm + Ví dụ) và bài học sinh nhìn thấy sẽ trống 4 mục. Mỗi phần
một lần gọi model riêng -> +4 request/đơn vị. Bỏ qua phần đã có nội dung, nên
chạy lại chỉ bù phần còn thiếu; kèm --force thì soạn lại cả phần đã có.

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
from app.lessons import bo_cuc as bo_cuc_svc
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


# Bốn phần mà `ingest_draft` KHÔNG sinh (nó chỉ lo Kiến thức trọng tâm + Ví dụ).
# Mỗi phần một lần gọi model riêng qua `ingest.soan_phan`, vì mỗi phần có yêu cầu
# rất khác nhau (Khởi động không được đưa đáp án, Bài tập không được kèm lời giải)
# — nhồi cả bốn vào một prompt là ra bốn khối lai lai giống nhau.
_PHAN_THEM = ("khoi_dong", "hoat_dong", "luyen_tap", "bai_tap")


def _thieu_phan(c: TopicContent) -> bool:
    """Còn phần nào trong 4 phần chưa có nội dung?"""
    return any(not (getattr(c, bo_cuc_svc.cot_cua(pid), "") or "").strip()
               for pid in _PHAN_THEM)


def _thieu_media(c: TopicContent) -> bool:
    return not json.loads(c.minh_hoa_json or "[]")


async def _soan_phan_them(session, topic, c, force: bool) -> tuple[int, list[str]]:
    """Soạn 4 phần còn lại. Bỏ qua phần đã có nội dung (trừ khi --force)."""
    xong, loi = 0, []
    for pid in _PHAN_THEM:
        cot = bo_cuc_svc.cot_cua(pid)
        if cot is None:
            continue
        if (getattr(c, cot, "") or "").strip() and not force:
            continue
        try:
            html = await ingest_svc.soan_phan(session, topic.id, pid)
        except LLMUnavailable:
            loi.append(f"{pid}: AI quá tải")
            continue
        if html:
            setattr(c, cot, html)
            xong += 1
        else:
            loi.append(f"{pid}: AI không soạn được")
    return xong, loi


async def seed(*, mon: str, khoi: str, publish: bool, force: bool, media: bool,
               phan: bool) -> None:
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
        # Chọn việc theo TỪNG MẢNH còn thiếu, không phải "đã có bản ghi thì bỏ
        # qua". Cửa lọc cũ loại mọi đơn vị đã có TopicContent, nên `--phan` trên
        # bộ nội dung đã soạn chạy ra 0 đơn vị — đúng ca dùng thật trên server:
        # 21 bài đều có Kiến thức + Ví dụ, chỉ thiếu 4 phần kia.
        todo, viec = [], {}
        for t in topics:
            c = cu.get(t.id)
            can_chu = c is None or force            # ingest_draft + quiz (tầng mạnh)
            can_phan = phan and (force or c is None or _thieu_phan(c))
            can_media = media and (force or c is None or _thieu_media(c))
            if can_chu or can_phan or can_media:
                todo.append(t)
                viec[t.id] = (can_chu, can_phan, can_media)
        n_chu = sum(1 for v in viec.values() if v[0])
        print(f"Tổng {len(topics)} đơn vị · đã có nội dung {len(cu)} · sẽ xử {len(todo)} "
              f"(soạn lại chữ: {n_chu} · bổ sung phần/media: {len(todo) - n_chu})")
        ghi_de = sum(1 for t in todo if t.id in cu and viec[t.id][0])
        if ghi_de:
            print(f"⚠️  --force: GHI ĐÈ khái niệm/ví dụ/quiz của {ghi_de} đơn vị đã có "
                  "— mất phần chuyên gia chỉnh tay. Giữ lại minh hoạ"
                  + (" và xuất bản luôn." if publish else " + trạng thái xuất bản hiện tại."))

        ok = fail = 0
        for i, t in enumerate(todo, 1):
            label = f"[{i}/{len(todo)}] {t.don_vi_kien_thuc[:52]}"
            can_chu, can_phan, can_media = viec[t.id]
            try:
                c = cu.get(t.id)
                if c is None:
                    c = TopicContent(topic_id=t.id, minh_hoa_json="[]", trang_thai=trang_thai)
                    session.add(c)
                elif publish:
                    c.trang_thai = "published"   # --publish là yêu cầu tường minh

                draft = {"khai_niem": "", "vi_du": [], "anh": [], "video": None, "mon": None}
                if can_chu:
                    draft = await ingest_svc.ingest_draft(session, t.id)
                    try:
                        quiz = await quiz_svc.generate_quiz(session, t.id)
                    except LLMUnavailable:
                        quiz = []
                    c.khai_niem = draft.get("khai_niem", "")
                    c.vi_du_json = json.dumps(draft.get("vi_du", []), ensure_ascii=False)
                    c.quiz_json = json.dumps(quiz, ensure_ascii=False)
                    # Cờ AI là cột riêng — KHÔNG nhét chuỗi đánh dấu vào `nguon`
                    # nữa, ô đó dành cho tư liệu chuyên gia dán vào.
                    c.ai_soan = True
                else:
                    quiz = json.loads(c.quiz_json or "[]")
                so_phan, loi_phan = 0, []
                if can_phan:
                    # flush trước: `soan_phan` đọc lại `khai_niem` từ DB để phần
                    # Luyện tập bám đúng lý thuyết vừa soạn, không phải kiến thức
                    # chung chung của mô hình.
                    await session.flush()
                    so_phan, loi_phan = await _soan_phan_them(session, t, c, force)
                loi_media: list[str] = []
                if can_media:
                    if not draft["anh"] and draft["video"] is None:
                        # Bài đã có chữ -> chỉ cần ĐỀ XUẤT media (tầng rẻ), không
                        # gọi lại ingest_draft (tầng mạnh) cho thứ đã có.
                        draft = {**draft, **await ingest_svc.goi_y_media(
                            t.don_vi_kien_thuc or "", t.mach_noi_dung or "",
                            bo_cuc_svc.noi_dung(c, "kien_thuc") or c.khai_niem or "")}
                    mh, loi_media = await _sinh_media(
                        session, t, draft, json.loads(c.minh_hoa_json or "[]"))
                    c.minh_hoa_json = json.dumps(mh, ensure_ascii=False)
                await session.commit()
                for m_ in loi_media + loi_phan:
                    print(f"    ⚠️  {m_}")
                ok += 1
                mo_ta = (f"khái niệm {'có' if draft.get('khai_niem') else 'trống'}, "
                         f"{len(draft.get('vi_du', []))} ví dụ, {len(quiz)} câu quiz"
                         if can_chu else "giữ chữ đã có")
                print(f"  ✓ {label} — {mo_ta}"
                      + (f", +{so_phan} phần" if can_phan else "")
                      + (f", +{len(json.loads(c.minh_hoa_json or '[]'))} minh hoạ"
                         if can_media else "")
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
    ap.add_argument("--phan", action="store_true",
                    help="Soạn cả Khởi động / Hoạt động / Luyện tập / Bài tập "
                         "(+4 request/đơn vị). Không có cờ này thì chỉ ra 2/7 mục.")
    args = ap.parse_args()
    asyncio.run(seed(mon=args.mon, khoi=args.khoi, publish=args.publish,
                     force=args.force, media=args.media, phan=args.phan))


if __name__ == "__main__":
    main()

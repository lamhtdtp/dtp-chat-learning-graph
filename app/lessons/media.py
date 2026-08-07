"""Sinh THẬT minh hoạ ② cho 1 đơn vị kiến thức từ đề xuất của AI ingest.

- ẢNH: gọi thẳng gateway.generate_image (đồng bộ trong request) rồi ghi vào
  storage -> có URL xem được ngay trong nháp.
- VIDEO: KHÔNG render đồng bộ được. Pipeline video cần Celery worker + công cụ
  host (TTS `say`, KaTeX node — xem app/video/tasks.py), mỗi video mất hàng chục
  giây tới vài phút. Nên ở đây chỉ tạo/tái dùng VideoJob rồi đẩy hàng đợi, đúng
  luồng học sinh bấm "Tạo video" (app/api/video.generate_video). Item minh hoạ
  mang theo `concept_key` để lần sau mở bài là tra được job đã DONE chưa.

Mọi lỗi sinh media đều KHÔNG được làm vỡ nháp nội dung: chữ (khái niệm + ví dụ)
là phần chính, ảnh/video là phần đính kèm. Lỗi -> bỏ qua item đó và ghi vào
`loi` để CMS hiện cho tác giả biết vì sao thiếu.
"""
import hashlib
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import CurriculumTopic
from app.llm import gateway
from app.llm.gateway import LLMUnavailable
from app.video import cache as video_cache
from app.video import storage
from app.video.concept import free_concept_key

log = logging.getLogger(__name__)

# Ảnh minh hoạ trong bài đọc theo chiều ngang -> khổ ngang. Cùng bộ size mà
# gateway.generate_image đã verify.
_IMG_SIZE = "1536x1024"


def _img_name(topic_id: int, prompt: str) -> str:
    """Tên file tất định theo (topic, prompt): bấm "Gợi ý AI" lại với cùng prompt
    thì ghi đè đúng file cũ, không rải thêm rác vào storage."""
    h = hashlib.sha1(prompt.encode()).hexdigest()[:16]
    return f"ai_topic{topic_id}_{h}.png"


async def generate_images(topic_id: int, goi_y: list[dict]) -> tuple[list[dict], list[str]]:
    """Sinh ảnh cho từng đề xuất {prompt, caption}. Trả (media, loi).

    Ảnh nào lỗi thì bỏ ảnh đó — không kéo cả nháp xuống theo.
    """
    media: list[dict] = []
    loi: list[str] = []
    for g in goi_y:
        prompt = g.get("prompt", "")
        if not prompt:
            continue
        try:
            data = await gateway.generate_image(prompt, size=_IMG_SIZE)
        except LLMUnavailable as e:
            loi.append("Chưa sinh được ảnh (AI đang quá tải, thử lại sau).")
            log.warning("sinh ảnh minh hoạ thất bại (topic=%s): %s", topic_id, e)
            continue
        except Exception as e:  # noqa: BLE001 - lỗi lạ từ SDK ảnh không được làm vỡ nháp
            loi.append("Chưa sinh được ảnh (lỗi từ dịch vụ sinh ảnh).")
            log.exception("lỗi sinh ảnh minh hoạ (topic=%s): %s", topic_id, e)
            continue
        url = storage.save_image(data, _img_name(topic_id, prompt))
        media.append({"type": "image", "url": url, "source": "ai",
                      "caption": g.get("caption") or "Hình minh hoạ"})
    return media, loi


async def request_video(
    session: AsyncSession, topic: CurriculumTopic, goi_y: dict, *, mon: str
) -> tuple[dict | None, list[str]]:
    """Tạo/tái dùng job video cho chủ đề AI đề xuất + đẩy hàng đợi. Trả (media, loi).

    `concept_key` free-key mã hoá (mon, chủ đề) nên cùng chủ đề -> cùng key ->
    dùng lại video đã render, không render trùng (app/video/cache).
    """
    chu_de = (goi_y or {}).get("chu_de", "").strip()
    if not chu_de:
        return None, []

    key = free_concept_key(chu_de, mon, settings.sgk_version)
    job, created = await video_cache.get_or_create_job(session, key, settings.sgk_version)
    if created:
        try:
            from app.ingestion.celery_app import render_video_task

            render_video_task.delay(job_id=job.id)
        except Exception as e:  # noqa: BLE001 - broker down không được làm vỡ request
            log.warning("không đẩy được job video %s vào hàng đợi: %s", job.id, e)
            return ({"type": "video", "url": None, "source": "ai", "concept_key": key,
                     "caption": goi_y.get("caption") or "Video minh hoạ"},
                    ["Đã tạo yêu cầu video nhưng hàng đợi chưa nhận — video sẽ dựng khi worker chạy lại."])
    return ({"type": "video", "url": job.video_url, "source": "ai", "concept_key": key,
             "caption": goi_y.get("caption") or "Video minh hoạ"}, [])


async def fill_video_urls(session: AsyncSession, media: list[dict]) -> list[dict]:
    """Điền `url` cho các item video AI còn trống bằng job đã DONE.

    Nháp lưu lúc video chưa render xong sẽ có url=None; hàm này gọi khi ĐỌC nội
    dung (CMS lẫn trang học) để video xuất hiện ngay khi job xong, không cần tác
    giả bấm lại "Gợi ý AI". Không tự lưu — chỉ làm giàu payload trả về.
    """
    out = []
    for m in media:
        key = m.get("concept_key")
        if m.get("type") == "video" and not m.get("url") and key:
            job = await video_cache.get_done_video(session, key, settings.sgk_version)
            if job and job.video_url:
                m = {**m, "url": job.video_url}
        out.append(m)
    return out

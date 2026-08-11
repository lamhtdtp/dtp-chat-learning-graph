"""Semantic cache cho lời gọi LLM tầng rẻ (qa, review_suggestion).

Key BẮT BUỘC gồm đủ ngữ cảnh phân biệt: task + mon + khoi + chuong + role —
thiếu một chiều là trả nhầm cache của khối/vai trò khác (xem skill
infra-observability Phần A). Câu hỏi được CHUẨN HOÁ trước khi băm để bắt các
biến thể vụn vặt (hoa/thường, khoảng trắng, dấu câu cuối) — "semantic" ở mức
chuẩn hoá bề mặt.

Ghi chú phạm vi: đây CHƯA phải semantic cache đầy đủ bằng embedding
nearest-neighbor (bắt câu diễn đạt khác hẳn nhưng cùng ý). Bản embedding-NN
để nâng cấp sau; bản này đã cắt được chi phí cho câu hỏi lặp/gần trùng và là
logic deterministic, test được (TDD).
"""

import hashlib
import logging
import re

import redis.asyncio as aioredis

from app.config import settings

log = logging.getLogger(__name__)

_CACHEABLE_TASKS = {"qa", "review_suggestion"}
_TTL_SECONDS = 24 * 3600


def _normalize(question: str) -> str:
    text = question.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text.rstrip(" ?.!。")


def build_cache_key(
    task: str,
    question: str,
    *,
    mon: str,
    khoi: str,
    chuong: int | None,
    role: str,
) -> str:
    raw = "|".join([task, mon, khoi, str(chuong), role, _normalize(question)])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"llmcache:{digest}"


def is_cacheable(task: str) -> bool:
    return task in _CACHEABLE_TASKS


_client: aioredis.Redis | None = None


def _redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


# Đã cảnh báo Redis hỏng chưa. Mỗi câu hỏi là 1 get + 1 set, Redis chết là log
# ngập hai dòng WARNING mỗi lượt; chỉ kêu to lần đầu, im cho tới khi nối lại được.
_da_bao = False


def _bao_hong(viec: str, exc: Exception) -> None:
    global _da_bao
    if not _da_bao:
        _da_bao = True
        log.warning("Semantic cache hỏng (%s): %s — bỏ qua cache, vẫn trả lời bình thường.", viec, exc)
    else:
        log.debug("Semantic cache vẫn hỏng (%s): %s", viec, exc)


async def get(key: str) -> str | None:
    """Đọc cache. Redis lỗi -> coi như KHÔNG có cache (fail-open).

    Cache chỉ là thứ tiết kiệm tiền và thời gian; Redis chết mà để 500 thì học
    sinh không hỏi được câu nào vì một hạ tầng PHỤ — đúng cái đã xảy ra trên prod
    khi Redis bật mật khẩu còn REDIS_URL thì chưa có (AuthenticationError).
    Hạn mức lượt/ngày đã fail-open từ trước; chỗ này bỏ sót."""
    global _da_bao
    try:
        v = await _redis().get(key)
    except Exception as exc:  # noqa: BLE001 — mất kết nối, sai mật khẩu, timeout…
        _bao_hong("đọc", exc)
        return None
    _da_bao = False
    return v


async def set(key: str, value: str, ttl: int = _TTL_SECONDS) -> None:
    """Ghi cache. Redis lỗi -> bỏ qua: câu trả lời đã sinh xong rồi, không có lý
    do gì để việc lưu lại làm hỏng lượt hỏi của học sinh."""
    try:
        await _redis().set(key, value, ex=ttl)
    except Exception as exc:  # noqa: BLE001
        _bao_hong("ghi", exc)


async def incr_quota(key: str, ttl: int) -> int:
    """Tăng bộ đếm hạn mức (vd lượt chat/ngày) và trả giá trị mới. Đặt TTL ở lần
    đầu để key tự hết hạn (dọn rác). Atomic qua Redis INCR."""
    r = _redis()
    n = await r.incr(key)
    if n == 1:
        await r.expire(key, ttl)
    return n

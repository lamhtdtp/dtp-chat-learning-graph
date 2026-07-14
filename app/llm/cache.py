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
import re

import redis.asyncio as aioredis

from app.config import settings

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


async def get(key: str) -> str | None:
    return await _redis().get(key)


async def set(key: str, value: str, ttl: int = _TTL_SECONDS) -> None:
    await _redis().set(key, value, ex=ttl)


async def incr_quota(key: str, ttl: int) -> int:
    """Tăng bộ đếm hạn mức (vd lượt chat/ngày) và trả giá trị mới. Đặt TTL ở lần
    đầu để key tự hết hạn (dọn rác). Atomic qua Redis INCR."""
    r = _redis()
    n = await r.incr(key)
    if n == 1:
        await r.expire(key, ttl)
    return n

import logging
"""LLM Gateway — mọi lời gọi model đi qua đây, node KHÔNG được gọi SDK provider
trực tiếp (xem skill rag-orchestration Phần D, infra-observability Phần A).

Provider thực tế: **VNGCloud AI Platform (MaaS)**, KHÔNG phải Google AI trực
tiếp như dự tính ban đầu trong spec. Đã verify qua API thật (không phải giả
định) — và phát hiện platform này KHÔNG dùng 1 giao thức thống nhất cho mọi
model, mà tuỳ TỪNG model cụ thể:
  - `gemini/gemini-2.5-pro`   -> **Anthropic SDK** (`client.messages.create`).
  - `gemini/gemini-2.5-flash` -> **OpenAI SDK** (`client.chat.completions.create`)
    — gọi qua Anthropic messages.create cho model này 404 "not found".
  - `gemini/gemini-embedding-001` -> **OpenAI SDK** (`client.embeddings.create`)
    — Anthropic không có API embeddings chuẩn.
  - `gemini/gemini-2.5-flash-lite` thử cả 2 giao thức đều lỗi (404 / IAM) —
    CHƯA dùng được trên key hiện tại.
Cùng 1 base_url + API key cho mọi model, chỉ khác SDK/giao thức gọi ra sao.
Vì giao thức gắn với TỪNG model (không suy được từ tên hay từ /v1/models —
field model_type ở đó không khớp giao thức thực tế gọi được), `_PROTOCOL_BY_MODEL`
dưới đây liệt kê tường minh, đã verify từng cái — KHÔNG suy đoán cho model mới,
phải tự test trước khi thêm vào.

CHƯA nối Langfuse (tracing) — cần LANGFUSE_HOST/KEY thật để verify, chưa có
lúc viết module này. Xem specs/full-system-spec.md mục 8.
"""

from typing import Literal

import anthropic
import openai
from openai import AsyncOpenAI

from app.config import settings
from app.llm import cache

Tier = Literal["cheap", "strong"]
Protocol = Literal["anthropic_messages", "openai_chat"]


class LLMUnavailable(Exception):
    """LLM provider tạm không phục vụ được (hết quota/429, mất kết nối). Tách
    khỏi lỗi lập trình để tầng API map sang 503 + thông báo thân thiện, thay vì
    500 trần (VNGCloud giới hạn 50 req/ngày -> 429 rất hay gặp)."""


# Lỗi provider coi là "tạm thời, thử lại sau" (429/quota + mất kết nối), gộp cả
# 2 SDK vì gateway dùng cả Anthropic lẫn OpenAI.
log = logging.getLogger(__name__)

_TRANSIENT_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
)

# Model không tồn tại / tài khoản không có quyền dùng nó -> provider trả 404.
# Đây là lỗi CẤU HÌNH, không phải tạm thời, nên trước đây nó xuyên qua gateway
# thành HTTP 500 trơ trọi: log chỉ có traceback NotFoundError, không nói model
# nào sai. Gói lại thành LLMUnavailable để mọi endpoint đã bắt LLMUnavailable
# trả 503 với lời nhắn tử tế, CÒN LOG thì nêu đúng tên model + việc phải làm.
_MODEL_ERRORS = (openai.NotFoundError, anthropic.NotFoundError)


def _loi_model(model: str, e: Exception) -> LLMUnavailable:
    log.error(
        "Model %r bị provider từ chối (%s): %s. Kiểm: (1) `python -m app.llm.tu_kiem` "
        "xem tài khoản có model nào; (2) GEMINI_MODEL_CHEAP/STRONG, EMBEDDING_MODEL "
        "trong .env; (3) gói/quota trên Console VNGCloud.",
        model, type(e).__name__, str(e)[:200])
    return LLMUnavailable(f"model {model} không dùng được")

TASK_TIER: dict[str, Tier] = {
    "route_intent": "cheap",
    "qa": "cheap",
    "review_suggestion": "cheap",
    # OCR CỐ Ý ở tầng rẻ (khác dự tính ban đầu "strong"): so sánh thật trên
    # trang SGK dày công thức (data/books/maths/6/1/30.png) cho thấy tầng rẻ
    # flash-lite OCR nhanh gấp ~8x, rẻ hơn ~5x, và TRUNG THỰC hơn — giữ đúng
    # ký hiệu gốc (vd "23.8", "2^2.25") thay vì tự diễn giải dấu "." thành "×"
    # như model đốt-reasoning làm. OCR không cần suy luận, chỉ cần trích xuất
    # đúng. Nếu eval OCR sau này cho thấy flash-lite kém trên trang hình học,
    # đổi task này sang "strong" — chỉ 1 dòng.
    "ocr_page": "cheap",
    "summarize_page": "cheap",  # tóm tắt trang SGK cho modal xem trang (rẻ, ngắn)
    # Kịch bản video bám câu trả lời ĐÃ grounding sẵn (chỉ diễn đạt lại, không
    # cần suy luận mới) -> tầng rẻ đủ dùng, rẻ cho tính năng đính kèm.
    "video_script": "cheap",
    # Gợi ý ánh xạ tag Itest -> taxonomy (EPIC-10, US-22): phân loại 1 tên đề vào
    # mạch/đơn vị kiến thức + mức độ có sẵn — việc phân loại nhẹ, tầng rẻ đủ; kết
    # quả LÀ ĐỀ XUẤT, người duyệt xác nhận mới dùng nên sai sót được chặn ở khâu duyệt.
    "itest_map": "cheap",
    "solve": "strong",
    "exam_gen": "strong",
    # Sinh trắc nghiệm "Kiểm tra nhanh" cho 1 đơn vị kiến thức theo ma trận
    # (yêu cầu cần đạt + mức độ). Cần suy luận để đặt phương án nhiễu hợp lý ->
    # tầng mạnh. Kết quả cache vào topic_content.quiz_json, không sinh lại mỗi lần.
    "quiz_gen": "strong",
    # Soạn nháp nội dung bài học từ nguồn (CMS AI ingest): khái niệm + ví dụ.
    "lesson_ingest": "strong",
    # Đề xuất minh hoạ (ảnh + video ngắn) cho nội dung ĐÃ soạn — chỉ mô tả lại
    # thành câu lệnh sinh ảnh, không suy luận chuyên môn -> tầng rẻ đủ. Tách khỏi
    # lesson_ingest vì gộp chung thì model hay bỏ rơi phần này (xem _prompt_media).
    "media_suggest": "cheap",
}

# Đã verify từng model một qua API thật — xem docstring trên. Thêm model mới
# vào đây CHỈ SAU KHI đã tự gọi thử và biết chắc giao thức nào hoạt động.
# Lưu ý: giao thức KHÔNG suy được từ tên — gemini-2.5-pro dùng Anthropic
# messages, nhưng gemini-3.1-pro-preview lại dùng OpenAI chat; cùng "pro".
_PROTOCOL_BY_MODEL: dict[str, Protocol] = {
    "gemini/gemini-2.5-pro": "anthropic_messages",
    "gemini/gemini-2.5-flash": "openai_chat",
    "gemini/gemini-3.1-flash-lite": "openai_chat",
    # Verify thật 2026-09-04 qua /v1/chat/completions: text tiếng Việt OK, nhận cả
    # role system lẫn assistant, max_tokens=16384 + trả JSON hợp lệ OK, và ĐỌC
    # ĐƯỢC ẢNH (thử data/books/maths/6/1/30.png -> tả đúng "thứ tự thực hiện phép
    # tính"). Nên dùng được cho cả ocr_page, không chỉ text.
    "google/gemma-4-31b-it": "openai_chat",
    "gemini/gemini-3.1-pro-preview": "openai_chat",
}


def _model_for_task(task: str) -> str:
    try:
        tier = TASK_TIER[task]
    except KeyError:
        raise ValueError(f"Task không xác định trong TASK_TIER: {task!r}") from None
    return settings.gemini_model_cheap if tier == "cheap" else settings.gemini_model_strong


def _protocol_for_model(model: str) -> Protocol:
    try:
        return _PROTOCOL_BY_MODEL[model]
    except KeyError:
        raise ValueError(
            f"Chưa xác định giao thức gọi cho model {model!r} — verify qua API thật "
            "trước khi thêm vào _PROTOCOL_BY_MODEL, đừng đoán."
        ) from None


def _anthropic_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        api_key="unused-auth-via-header",  # auth thật qua header Authorization dưới đây
        base_url=settings.ai_platform_base_url,
        default_headers={"Authorization": f"Bearer {settings.ai_platform_api_key}"},
    )


def _openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.ai_platform_base_url.rstrip("/") + "/v1",
        api_key=settings.ai_platform_api_key,
    )


def _to_openai_content(content: str | list[dict]) -> str | list[dict]:
    """Content block text giống hệt nhau giữa Anthropic/OpenAI — chỉ ảnh khác
    hình dạng: Anthropic dùng {"type": "image", "source": {...}}, OpenAI dùng
    {"type": "image_url", "image_url": {"url": "data:...;base64,..."}}."""
    if isinstance(content, str):
        return content
    converted = []
    for block in content:
        if block.get("type") == "image":
            source = block["source"]
            converted.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{source['media_type']};base64,{source['data']}"},
                }
            )
        else:
            converted.append(block)
    return converted


async def _complete_anthropic(model: str, messages: list[dict], max_tokens: int) -> str:
    client = _anthropic_client()
    response = await client.messages.create(model=model, max_tokens=max_tokens, messages=messages)
    return "".join(block.text for block in response.content if block.type == "text")


async def _complete_openai(model: str, messages: list[dict], max_tokens: int) -> str:
    openai_messages = [{"role": m["role"], "content": _to_openai_content(m["content"])} for m in messages]
    client = _openai_client()
    response = await client.chat.completions.create(model=model, max_tokens=max_tokens, messages=openai_messages)
    return response.choices[0].message.content or ""


async def complete(
    task: str,
    messages: list[dict],
    max_tokens: int = 4096,
    cache_ctx: dict | None = None,
) -> str:
    """`messages` LUÔN viết theo format Anthropic (kể cả khi model đích dùng
    giao thức OpenAI — gateway tự chuyển đổi, xem `_to_openai_content`):
    [{"role": "user"|"assistant", "content": str | list[content_block]}].
    Content block ảnh (dùng cho task="ocr_page"): {"type": "image", "source":
    {"type": "base64", "media_type": "image/png", "data": <base64 str>}}.

    `cache_ctx` (tuỳ chọn): dict {question, mon, khoi, chuong, role} để bật
    semantic cache cho task tầng rẻ cacheable (qa, review_suggestion). Node
    truyền vào; task khác/None thì bỏ qua cache. Cache dùng Redis (xem
    app.llm.cache).

    Các model đốt reasoning token (tầng mạnh gemini-3.1-pro-preview đốt
    ~2400 token "suy nghĩ" ẩn TÍNH VÀO max_tokens nhưng không hiện trong
    output) — max_tokens quá thấp trả về text rỗng/bị cắt dù không báo lỗi
    (đã gặp thật khi verify API), nên mặc định để cao 4096. Tầng rẻ
    flash-lite gần như không đốt reasoning nên không tốn thừa.
    """
    use_cache = cache_ctx is not None and cache.is_cacheable(task)
    key: str | None = None
    if use_cache:
        key = cache.build_cache_key(task, cache_ctx["question"], mon=cache_ctx["mon"],
                                    khoi=cache_ctx["khoi"], chuong=cache_ctx.get("chuong"),
                                    role=cache_ctx["role"])
        hit = await cache.get(key)
        if hit is not None:
            return hit

    model = _model_for_task(task)
    protocol = _protocol_for_model(model)
    try:
        if protocol == "anthropic_messages":
            answer = await _complete_anthropic(model, messages, max_tokens)
        else:
            answer = await _complete_openai(model, messages, max_tokens)
    except _MODEL_ERRORS as e:
        raise _loi_model(model, e) from e
    except _TRANSIENT_ERRORS as e:
        raise LLMUnavailable(str(e)) from e

    if use_cache and key is not None and answer.strip():
        await cache.set(key, answer)
    return answer


async def embed(texts: list[str]) -> list[list[float]]:
    client = _openai_client()
    try:
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=texts,
            encoding_format="float",
        )
    except _MODEL_ERRORS as e:
        raise _loi_model(settings.embedding_model, e) from e
    except _TRANSIENT_ERRORS as e:
        raise LLMUnavailable(str(e)) from e
    return [item.embedding for item in response.data]


async def generate_image(prompt: str, *, size: str = "1536x1024") -> bytes:
    """Sinh 1 ảnh (bytes PNG) qua model ảnh trên VNGCloud (OpenAI SDK
    images.generate, đã verify với openai/gpt-image-1). Dùng làm nền cảnh cho
    video kiểu explainer AI (app/video/scene.py)."""
    import base64

    client = _openai_client()
    try:
        response = await client.images.generate(
            model=settings.image_model, prompt=prompt, size=size, n=1,
        )
    except _MODEL_ERRORS as e:
        raise _loi_model(settings.image_model, e) from e
    except _TRANSIENT_ERRORS as e:
        raise LLMUnavailable(str(e)) from e
    return base64.b64decode(response.data[0].b64_json)

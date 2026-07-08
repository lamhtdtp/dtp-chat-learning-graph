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
from openai import AsyncOpenAI

from app.config import settings

Tier = Literal["cheap", "strong"]
Protocol = Literal["anthropic_messages", "openai_chat"]

TASK_TIER: dict[str, Tier] = {
    "route_intent": "cheap",
    "qa": "cheap",
    "review_suggestion": "cheap",
    "solve": "strong",
    "ocr_page": "strong",
    "exam_gen": "strong",
}

# Đã verify từng model một qua API thật — xem docstring trên. Thêm model mới
# vào đây CHỈ SAU KHI đã tự gọi thử và biết chắc giao thức nào hoạt động.
_PROTOCOL_BY_MODEL: dict[str, Protocol] = {
    "gemini/gemini-2.5-pro": "anthropic_messages",
    "gemini/gemini-2.5-flash": "openai_chat",
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


async def complete(task: str, messages: list[dict], max_tokens: int = 2048) -> str:
    """`messages` LUÔN viết theo format Anthropic (kể cả khi model đích dùng
    giao thức OpenAI — gateway tự chuyển đổi, xem `_to_openai_content`):
    [{"role": "user"|"assistant", "content": str | list[content_block]}].
    Content block ảnh (dùng cho task="ocr_page"): {"type": "image", "source":
    {"type": "base64", "media_type": "image/png", "data": <base64 str>}}.

    gemini-2.5-pro qua gateway này tốn token "suy nghĩ" ẩn không hiện trong
    output — max_tokens quá thấp (vd 100) có thể trả về text rỗng dù
    stop_reason="end_turn" (đã gặp thật khi verify API), nên mặc định 2048.
    """
    model = _model_for_task(task)
    protocol = _protocol_for_model(model)
    if protocol == "anthropic_messages":
        return await _complete_anthropic(model, messages, max_tokens)
    return await _complete_openai(model, messages, max_tokens)


async def embed(texts: list[str]) -> list[list[float]]:
    client = _openai_client()
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        encoding_format="float",
    )
    return [item.embedding for item in response.data]

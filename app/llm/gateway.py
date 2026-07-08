"""LLM Gateway — mọi lời gọi model đi qua đây, node KHÔNG được gọi SDK provider
trực tiếp (xem skill rag-orchestration Phần D, infra-observability Phần A).

Provider thực tế: **VNGCloud AI Platform (MaaS)**, KHÔNG phải Google AI trực
tiếp như dự tính ban đầu trong spec — đã verify qua API thật, không phải giả
định:
  - Chat/vision (model có model_type="messages" trên VNGCloud, vd
    gemini-2.5-pro) -> gọi qua **Anthropic SDK** (`client.messages.create`).
  - Embedding (model_type="embedding", vd gemini-embedding-001) -> gọi qua
    **OpenAI SDK** (`client.embeddings.create`) — Anthropic không có API
    embeddings chuẩn.
Cùng 1 base_url + API key cho cả 2, chỉ khác SDK/giao thức dùng để gọi.

CHƯA nối Langfuse (tracing) — cần LANGFUSE_HOST/KEY thật để verify, chưa có
lúc viết module này. Xem specs/full-system-spec.md mục 8.
"""

from typing import Literal

import anthropic
from openai import AsyncOpenAI

from app.config import settings

Tier = Literal["cheap", "strong"]

# Tầng model theo task. Hiện CẢ HAI tầng trỏ cùng 1 model thật (gemini-2.5-pro)
# vì gemini-2.5-flash/flash-lite bị IAM_PERMISSION_DENIED trên key hiện có —
# đổi GEMINI_MODEL_CHEAP trong .env khi được cấp quyền, KHÔNG cần sửa code này.
TASK_TIER: dict[str, Tier] = {
    "route_intent": "cheap",
    "qa": "cheap",
    "review_suggestion": "cheap",
    "solve": "strong",
    "ocr_page": "strong",
    "exam_gen": "strong",
}


def _model_for_task(task: str) -> str:
    try:
        tier = TASK_TIER[task]
    except KeyError:
        raise ValueError(f"Task không xác định trong TASK_TIER: {task!r}") from None
    return settings.gemini_model_cheap if tier == "cheap" else settings.gemini_model_strong


def _chat_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        api_key="unused-auth-via-header",  # auth thật qua header Authorization dưới đây
        base_url=settings.ai_platform_base_url,
        default_headers={"Authorization": f"Bearer {settings.ai_platform_api_key}"},
    )


def _embedding_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.ai_platform_base_url.rstrip("/") + "/v1",
        api_key=settings.ai_platform_api_key,
    )


async def complete(task: str, messages: list[dict], max_tokens: int = 2048) -> str:
    """`messages` theo format Anthropic: [{"role": "user"|"assistant",
    "content": str | list[content_block]}]. Content block ảnh (dùng cho
    task="ocr_page"): {"type": "image", "source": {"type": "base64",
    "media_type": "image/png", "data": <base64 str>}}.

    gemini-2.5-pro qua gateway này tốn token "suy nghĩ" ẩn không hiện trong
    output — max_tokens quá thấp (vd 100) có thể trả về text rỗng dù
    stop_reason="end_turn" (đã gặp thật khi verify API), nên mặc định 2048.
    """
    client = _chat_client()
    response = await client.messages.create(
        model=_model_for_task(task),
        max_tokens=max_tokens,
        messages=messages,
    )
    return "".join(block.text for block in response.content if block.type == "text")


async def embed(texts: list[str]) -> list[list[float]]:
    client = _embedding_client()
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
        encoding_format="float",
    )
    return [item.embedding for item in response.data]

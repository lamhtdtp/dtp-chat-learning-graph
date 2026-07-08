"""Test thật qua VNGCloud AI Platform — không mock. Bỏ qua nếu thiếu credential
(CI sẽ không có .env thật). Đây là cách tự động hoá lại việc verify thủ công
đã làm khi mới nhận API key, để phát hiện sớm nếu VNGCloud đổi hành vi."""

import pytest

from app.config import settings
from app.llm import gateway

pytestmark = pytest.mark.skipif(
    not settings.ai_platform_api_key, reason="Cần AI_PLATFORM_API_KEY thật trong .env"
)


async def test_complete_that_qua_vngcloud():
    text = await gateway.complete(
        "qa", [{"role": "user", "content": "Trả lời đúng 1 câu: 2+2 bằng mấy?"}]
    )
    assert "4" in text


async def test_embed_that_qua_vngcloud():
    vectors = await gateway.embed(["xin chào"])

    assert len(vectors) == 1
    assert len(vectors[0]) == 3072

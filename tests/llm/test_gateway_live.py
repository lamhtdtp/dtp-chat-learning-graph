"""Test thật qua VNGCloud AI Platform — không mock. Bỏ qua nếu thiếu credential
(CI sẽ không có .env thật). Đây là cách tự động hoá lại việc verify thủ công
đã làm khi mới nhận API key, để phát hiện sớm nếu VNGCloud đổi hành vi — bao
gồm cả 2 giao thức khác nhau (tầng rẻ = OpenAI chat.completions, tầng mạnh =
Anthropic messages) vì đây chính là chỗ đã sai lệch với giả định ban đầu.
"""

from pathlib import Path

import pytest

from app.config import settings
from app.llm import gateway

pytestmark = pytest.mark.skipif(
    not settings.ai_platform_api_key, reason="Cần AI_PLATFORM_API_KEY thật trong .env"
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PAGE = REPO_ROOT / "data" / "books" / "maths" / "6" / "1" / "5.png"


async def test_complete_tang_re_that_qua_vngcloud():
    text = await gateway.complete(
        "qa", [{"role": "user", "content": "Trả lời đúng 1 câu: 2+2 bằng mấy?"}]
    )
    assert "4" in text


async def test_complete_tang_manh_that_qua_vngcloud():
    text = await gateway.complete(
        "solve", [{"role": "user", "content": "Trả lời đúng 1 câu: 2+2 bằng mấy?"}]
    )
    assert "4" in text


@pytest.mark.skipif(not SAMPLE_PAGE.exists(), reason="Cần ảnh trang SGK thật để test vision")
async def test_complete_vision_doc_dung_noi_dung_anh_that():
    import base64

    img_b64 = base64.standard_b64encode(SAMPLE_PAGE.read_bytes()).decode()
    text = await gateway.complete(
        "ocr_page",
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Trích nguyên văn tên Chương xuất hiện trên trang này."},
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
                    },
                ],
            }
        ],
    )
    assert "Số tự nhiên" in text


async def test_embed_that_qua_vngcloud():
    vectors = await gateway.embed(["xin chào"])

    assert len(vectors) == 1
    assert len(vectors[0]) == 3072

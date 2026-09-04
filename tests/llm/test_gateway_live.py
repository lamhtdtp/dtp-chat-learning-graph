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


async def _model_co_san() -> list[str]:
    """Model tài khoản THẬT SỰ được dùng. Rỗng/không gọi được -> []."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(settings.ai_platform_base_url.rstrip("/") + "/v1/models",
                            headers={"Authorization": f"Bearer {settings.ai_platform_api_key}"})
        if r.status_code != 200:
            return []
        return [x.get("id", "") for x in (r.json().get("data") or []) if isinstance(x, dict)]
    except Exception:  # noqa: BLE001 — mạng lỗi thì coi như không biết
        return []


async def test_embed_that_qua_vngcloud():
    """Bỏ qua khi tài khoản CHƯA được gán model embedding — đó là chuyện gói dịch
    vụ, không phải code sai. Nhưng nếu model CÓ trong danh sách mà vẫn lỗi thì
    phải đỏ: lúc đó là hồi quy thật.

    (2026-09-04: tài khoản chỉ có google/gemma-4-31b-it, không có embedding ->
    tra SGK bằng vector đang tắt, xem `python -m app.llm.tu_kiem`.)
    """
    if settings.embedding_model not in await _model_co_san():
        pytest.skip(f"tài khoản không có model embedding {settings.embedding_model!r} "
                    "-> tra cứu SGK bằng vector đang tắt")

    vectors = await gateway.embed(["xin chào"])

    assert len(vectors) == 1
    assert len(vectors[0]) == 3072

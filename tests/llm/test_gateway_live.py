"""Test thật qua VNGCloud AI Platform — không mock. Bỏ qua nếu thiếu credential
(CI sẽ không có .env thật). Đây là cách tự động hoá lại việc verify thủ công
đã làm khi mới nhận API key, để phát hiện sớm nếu VNGCloud đổi hành vi — bao
gồm cả 2 giao thức khác nhau (tầng rẻ = OpenAI chat.completions, tầng mạnh =
Anthropic messages) vì đây chính là chỗ đã sai lệch với giả định ban đầu.
"""

from pathlib import Path

import pytest

import openai

from app.config import settings
from app.ingestion import qdrant_store
from app.llm import gateway
from app.llm.gateway import LLMUnavailable

pytestmark = pytest.mark.skipif(
    not settings.ai_platform_api_key, reason="Cần AI_PLATFORM_API_KEY thật trong .env"
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PAGE = REPO_ROOT / "data" / "books" / "maths" / "6" / "1" / "5.png"


async def _bo_qua_neu_het_credit() -> None:
    """403 credit/budget = chuyện gói dịch vụ, không phải code sai -> skip có lý do.

    KHÔNG skip khi lỗi khác: 404 sai model hay 500 vẫn phải đỏ.
    """
    try:
        await gateway.complete(task="qa", messages=[{"role": "user", "content": "ping"}],
                               max_tokens=4)
    except LLMUnavailable as e:
        if "credit" in str(e):
            pytest.skip("tài khoản MaaS hết credit/budget -> bật TRO_LY_BAO_TRI=true "
                        "và nạp tiền trên Console VNGCloud")
    except Exception:  # noqa: BLE001 — lỗi khác thì để test thật chạy và đỏ
        return


async def test_complete_tang_re_that_qua_vngcloud():
    await _bo_qua_neu_het_credit()
    text = await gateway.complete(
        "qa", [{"role": "user", "content": "Trả lời đúng 1 câu: 2+2 bằng mấy?"}]
    )
    assert "4" in text


async def test_complete_tang_manh_that_qua_vngcloud():
    await _bo_qua_neu_het_credit()
    text = await gateway.complete(
        "solve", [{"role": "user", "content": "Trả lời đúng 1 câu: 2+2 bằng mấy?"}]
    )
    assert "4" in text


@pytest.mark.skipif(not SAMPLE_PAGE.exists(), reason="Cần ảnh trang SGK thật để test vision")
async def test_complete_vision_doc_dung_noi_dung_anh_that():
    await _bo_qua_neu_het_credit()
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
    tra SGK bằng vector đang tắt, xem `python -m app.llm.tu_kiem`.
     2026-09-08: đổi sang baai/bge-m3 sau khi text-embedding-3-large bị bỏ.)
    """
    if settings.embedding_model not in await _model_co_san():
        pytest.skip(f"tài khoản không có model embedding {settings.embedding_model!r} "
                    "-> tra cứu SGK bằng vector đang tắt")

    vectors = await gateway.embed(["xin chào"])

    assert len(vectors) == 1
    # So với hằng số Qdrant đang dùng, KHÔNG hardcode lại con số: lệch giữa hai
    # chỗ này nghĩa là upsert sẽ nổ lúc nạp sách, và đây là chỗ duy nhất phát
    # hiện được sớm bằng lời gọi thật.
    assert len(vectors[0]) == qdrant_store._EMBEDDING_DIM, (
        f"model {settings.embedding_model!r} trả {len(vectors[0])} chiều nhưng "
        f"qdrant_store._EMBEDDING_DIM = {qdrant_store._EMBEDDING_DIM}"
    )

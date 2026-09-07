"""Model không tồn tại phải thành 503 có log, KHÔNG phải 500 trơ.

Sự cố thật: gói VNGCloud hết model -> mọi lệnh gọi trả 404 "The requested model
is not found". 404 không nằm trong `_TRANSIENT_ERRORS` nên nó xuyên qua gateway
thành HTTP 500, log chỉ có traceback openai.NotFoundError — không nói model nào
sai, không nói phải làm gì.
"""
import httpx
import openai
import pytest

from app.config import settings
from app.llm import gateway
from app.llm.gateway import LLMUnavailable


def _404() -> openai.NotFoundError:
    req = httpx.Request("POST", "https://x/v1/chat/completions")
    res = httpx.Response(404, json={"message": "The requested model is not found"},
                         request=req)
    return openai.NotFoundError("model not found", response=res, body=None)


async def test_complete_404_thanh_LLMUnavailable_kem_ten_model(mocker, caplog):
    mocker.patch.object(gateway, "_complete_openai", side_effect=_404())
    with caplog.at_level("ERROR"):
        with pytest.raises(LLMUnavailable) as e:
            await gateway.complete(task="qa", messages=[{"role": "user", "content": "x"}])
    assert settings.gemini_model_cheap in str(e.value)
    # Log phải nêu ĐÚNG model sai + việc phải làm, không chỉ "lỗi provider".
    assert settings.gemini_model_cheap in caplog.text
    assert "tu_kiem" in caplog.text and "Console VNGCloud" in caplog.text


async def test_embed_404_bao_dung_ten_model_embedding(mocker, caplog):
    kh = mocker.Mock()
    kh.embeddings.create = mocker.AsyncMock(side_effect=_404())
    mocker.patch.object(gateway, "_openai_client", return_value=kh)
    with caplog.at_level("ERROR"):
        with pytest.raises(LLMUnavailable):
            await gateway.embed(["x"])
    # KHÔNG được nêu tên model chat — mỗi đường có model riêng, nêu sai là lần sai chỗ.
    assert settings.embedding_model in caplog.text
    assert settings.gemini_model_cheap not in caplog.text


async def test_generate_image_404_bao_dung_ten_model_anh(mocker, caplog):
    kh = mocker.Mock()
    kh.images.generate = mocker.AsyncMock(side_effect=_404())
    mocker.patch.object(gateway, "_openai_client", return_value=kh)
    with caplog.at_level("ERROR"):
        with pytest.raises(LLMUnavailable):
            await gateway.generate_image("a circle")
    assert settings.image_model in caplog.text


async def test_429_van_la_loi_tam_thoi_khong_doi_thong_diep(mocker):
    """Hết quota là chuyện khác hẳn — không được gộp vào lỗi cấu hình."""
    req = httpx.Request("POST", "https://x/v1/chat/completions")
    res = httpx.Response(429, json={"message": "rate limit"}, request=req)
    mocker.patch.object(gateway, "_complete_openai",
                        side_effect=openai.RateLimitError("rl", response=res, body=None))
    with pytest.raises(LLMUnavailable) as e:
        await gateway.complete(task="qa", messages=[{"role": "user", "content": "x"}])
    assert "không dùng được" not in str(e.value)


def _403() -> openai.PermissionDeniedError:
    req = httpx.Request("POST", "https://x/v1/chat/completions")
    res = httpx.Response(403, json={
        "message": "Access denied. Please check your MaaS credit balance, budget quota"},
        request=req)
    return openai.PermissionDeniedError("denied", response=res, body=None)


async def test_403_het_credit_thanh_503_kem_huong_xu_ly(mocker, caplog):
    """403 credit/budget cũng không nằm trong _TRANSIENT_ERRORS -> từng thành 500.

    Khác 429 (chờ là hết) và khác 404 (sai model): cái này phải nạp tiền, nên log
    phải nói ra điều đó và chỉ luôn cờ bảo trì để học sinh không thấy lỗi trần.
    """
    mocker.patch.object(gateway, "_complete_openai", side_effect=_403())
    with caplog.at_level("ERROR"):
        with pytest.raises(LLMUnavailable) as e:
            await gateway.complete(task="qa", messages=[{"role": "user", "content": "x"}])
    assert "credit" in str(e.value)
    assert "Console VNGCloud" in caplog.text and "TRO_LY_BAO_TRI" in caplog.text
    # KHÔNG được lẫn với lỗi sai model
    assert "bị provider từ chối" not in caplog.text

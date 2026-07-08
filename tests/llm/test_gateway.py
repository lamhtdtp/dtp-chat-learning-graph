from types import SimpleNamespace

import pytest

from app.config import settings
from app.llm import gateway


class _FakeTextBlock:
    def __init__(self, text: str, type_: str = "text"):
        self.type = type_
        self.text = text


def _fake_openai(mocker, content="xin chào"):
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=mocker.AsyncMock(return_value=fake_response))
        )
    )
    mocker.patch("app.llm.gateway._openai_client", return_value=fake_client)
    return fake_client


# Cấu hình hiện tại: cả tầng rẻ (flash-lite) lẫn tầng mạnh (3.1-pro-preview)
# đều gọi qua OpenAI protocol. ocr_page CỐ Ý ở tầng rẻ (xem TASK_TIER).
@pytest.mark.parametrize("task", ["route_intent", "qa", "review_suggestion", "ocr_page"])
async def test_complete_tang_re_dung_model_cheap_qua_openai(mocker, task):
    fake_client = _fake_openai(mocker)

    result = await gateway.complete(task, [{"role": "user", "content": "hi"}])

    assert result == "xin chào"
    assert fake_client.chat.completions.create.call_args.kwargs["model"] == settings.gemini_model_cheap


@pytest.mark.parametrize("task", ["solve", "exam_gen"])
async def test_complete_tang_manh_dung_model_strong_qua_openai(mocker, task):
    fake_client = _fake_openai(mocker)

    result = await gateway.complete(task, [{"role": "user", "content": "hi"}])

    assert result == "xin chào"
    assert fake_client.chat.completions.create.call_args.kwargs["model"] == settings.gemini_model_strong


async def test_complete_dinh_tuyen_anthropic_khi_model_la_2_5_pro(mocker):
    # gemini-2.5-pro vẫn nằm trong _PROTOCOL_BY_MODEL (anthropic_messages) dù
    # config mặc định không dùng — giữ nhánh này được test khi model đổi lại.
    mocker.patch.object(settings, "gemini_model_strong", "gemini/gemini-2.5-pro")
    fake_response = SimpleNamespace(content=[_FakeTextBlock("xin chào")])
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=mocker.AsyncMock(return_value=fake_response))
    )
    mocker.patch("app.llm.gateway._anthropic_client", return_value=fake_client)

    result = await gateway.complete("solve", [{"role": "user", "content": "hi"}])

    assert result == "xin chào"
    assert fake_client.messages.create.call_args.kwargs["model"] == "gemini/gemini-2.5-pro"


async def test_complete_anthropic_ghep_text_bo_qua_block_khac(mocker):
    mocker.patch.object(settings, "gemini_model_strong", "gemini/gemini-2.5-pro")
    fake_response = SimpleNamespace(
        content=[_FakeTextBlock("phần 1. "), _FakeTextBlock("ẩn", type_="thinking"), _FakeTextBlock("phần 2.")]
    )
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=mocker.AsyncMock(return_value=fake_response))
    )
    mocker.patch("app.llm.gateway._anthropic_client", return_value=fake_client)

    result = await gateway.complete("solve", [{"role": "user", "content": "hi"}])

    assert result == "phần 1. phần 2."


async def test_complete_chuyen_doi_block_anh_sang_dinh_dang_openai(mocker):
    fake_create = mocker.AsyncMock(
        return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="đọc được ảnh"))])
    )
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    mocker.patch("app.llm.gateway._openai_client", return_value=fake_client)

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "đọc ảnh này"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}},
            ],
        }
    ]
    await gateway.complete("ocr_page", messages)

    sent = fake_create.call_args.kwargs["messages"][0]["content"]
    assert sent[0] == {"type": "text", "text": "đọc ảnh này"}
    assert sent[1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}


async def test_complete_task_khong_ton_tai_bao_loi_ro_rang():
    with pytest.raises(ValueError, match="khong_ton_tai"):
        await gateway.complete("khong_ton_tai", [{"role": "user", "content": "hi"}])


async def test_complete_model_chua_ro_giao_thuc_bao_loi_ro_rang():
    with pytest.raises(ValueError, match="giao thức"):
        gateway._protocol_for_model("gemini/mot-model-chua-tung-test")


async def test_embed_tra_ve_vector_dung_thu_tu(mocker):
    fake_response = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.1, 0.2]), SimpleNamespace(embedding=[0.3, 0.4])]
    )
    fake_client = SimpleNamespace(
        embeddings=SimpleNamespace(create=mocker.AsyncMock(return_value=fake_response))
    )
    mocker.patch("app.llm.gateway._openai_client", return_value=fake_client)

    vectors = await gateway.embed(["a", "b"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]

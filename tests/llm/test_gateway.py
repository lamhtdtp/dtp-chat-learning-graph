from types import SimpleNamespace

import pytest

from app.config import settings
from app.llm import gateway


class _FakeTextBlock:
    def __init__(self, text: str, type_: str = "text"):
        self.type = type_
        self.text = text


@pytest.mark.parametrize(
    "task,expected_model_attr",
    [
        ("route_intent", "gemini_model_cheap"),
        ("qa", "gemini_model_cheap"),
        ("review_suggestion", "gemini_model_cheap"),
        ("solve", "gemini_model_strong"),
        ("ocr_page", "gemini_model_strong"),
        ("exam_gen", "gemini_model_strong"),
    ],
)
async def test_complete_chon_dung_tier_theo_task(mocker, task, expected_model_attr):
    fake_response = SimpleNamespace(content=[_FakeTextBlock("xin chào")])
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=mocker.AsyncMock(return_value=fake_response))
    )
    mocker.patch("app.llm.gateway._chat_client", return_value=fake_client)

    result = await gateway.complete(task, [{"role": "user", "content": "hi"}])

    assert result == "xin chào"
    called_model = fake_client.messages.create.call_args.kwargs["model"]
    assert called_model == getattr(settings, expected_model_attr)


async def test_complete_bo_qua_block_khong_phai_text(mocker):
    fake_response = SimpleNamespace(
        content=[_FakeTextBlock("phần 1. "), _FakeTextBlock("ẩn", type_="thinking"), _FakeTextBlock("phần 2.")]
    )
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=mocker.AsyncMock(return_value=fake_response))
    )
    mocker.patch("app.llm.gateway._chat_client", return_value=fake_client)

    result = await gateway.complete("qa", [{"role": "user", "content": "hi"}])

    assert result == "phần 1. phần 2."


async def test_complete_task_khong_ton_tai_bao_loi_ro_rang():
    with pytest.raises(ValueError, match="khong_ton_tai"):
        await gateway.complete("khong_ton_tai", [{"role": "user", "content": "hi"}])


async def test_embed_tra_ve_vector_dung_thu_tu(mocker):
    fake_response = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.1, 0.2]), SimpleNamespace(embedding=[0.3, 0.4])]
    )
    fake_client = SimpleNamespace(
        embeddings=SimpleNamespace(create=mocker.AsyncMock(return_value=fake_response))
    )
    mocker.patch("app.llm.gateway._embedding_client", return_value=fake_client)

    vectors = await gateway.embed(["a", "b"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]

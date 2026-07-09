import httpx
import openai
import pytest

from app.llm import gateway


def _rate_limit_error() -> openai.RateLimitError:
    resp = httpx.Response(429, request=httpx.Request("POST", "http://x/v1/chat"))
    return openai.RateLimitError("rate limit", response=resp, body=None)


async def test_complete_map_429_thanh_llm_unavailable(mocker):
    async def boom(*a, **k):
        raise _rate_limit_error()
    fake = mocker.Mock()
    fake.chat.completions.create = boom
    mocker.patch("app.llm.gateway._openai_client", return_value=fake)

    with pytest.raises(gateway.LLMUnavailable):
        await gateway.complete("qa", [{"role": "user", "content": "hi"}])


async def test_embed_map_429_thanh_llm_unavailable(mocker):
    async def boom(*a, **k):
        raise _rate_limit_error()
    fake = mocker.Mock()
    fake.embeddings.create = boom
    mocker.patch("app.llm.gateway._openai_client", return_value=fake)

    with pytest.raises(gateway.LLMUnavailable):
        await gateway.embed(["x"])

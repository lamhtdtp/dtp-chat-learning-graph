import pytest

from app.graph import router


@pytest.mark.parametrize("text", [
    "Tập hợp là gì?",
    "Số nguyên tố là gì thế nào",
    "Tại sao 0 là số tự nhiên?",
    "Định nghĩa ước chung",
])
def test_rule_based_nhan_dien_hoi_dap(text):
    assert router.route_rule_based(text) == "hoi_dap"


@pytest.mark.parametrize("text", [
    "Tính 2 + 3 x 5",
    "Giải bài này giúp em",
    "Tìm x biết x + 5 = 12",
    "Rút gọn biểu thức",
])
def test_rule_based_nhan_dien_giai_bai(text):
    assert router.route_rule_based(text) == "giai_bai"


def test_rule_based_khong_chac_tra_none():
    assert router.route_rule_based("Chào bạn") is None


async def test_route_intent_fallback_llm_khi_rule_khong_chac(mocker):
    llm = mocker.patch("app.graph.router.gateway.complete",
                       mocker.AsyncMock(return_value="giai_bai"))
    intent = await router.route_intent("Cho mình bài tương tự về đồng xu")

    assert intent == "giai_bai"
    assert llm.await_args.kwargs["task"] == "route_intent"


async def test_route_intent_khong_goi_llm_khi_rule_da_chac(mocker):
    llm = mocker.patch("app.graph.router.gateway.complete", mocker.AsyncMock())
    intent = await router.route_intent("Tập hợp là gì?")

    assert intent == "hoi_dap"
    llm.assert_not_awaited()

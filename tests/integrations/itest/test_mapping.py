"""US-22: LLM gợi ý ánh xạ (qua gateway), người duyệt xác nhận mới dùng, câu
chưa map được đánh dấu không âm thầm bỏ."""

import pytest

from app.integrations.itest import mapping
from app.integrations.itest.mapping import _parse_suggestion


def test_parse_suggestion_hop_le():
    assert _parse_suggestion('{"topic_id": 3, "muc_do": "kho"}', {1, 3}) == (3, "kho")


def test_parse_suggestion_khong_map():
    assert _parse_suggestion('{"khong_map": true}', {1, 3}) is None


def test_parse_suggestion_topic_khong_hop_le():
    assert _parse_suggestion('{"topic_id": 99, "muc_do": "de"}', {1, 3}) is None


def test_parse_suggestion_json_hong():
    assert _parse_suggestion("xin loi toi khong biet", {1, 3}) is None


def test_parse_suggestion_muc_do_la_mac_dinh_trung_binh():
    assert _parse_suggestion('{"topic_id": 1, "muc_do": "sieu kho"}', {1}) == (1, "trung_binh")


async def test_suggest_mapping_di_qua_gateway(mocker):
    """Đề xuất phải đi qua app.llm.gateway (được trace) — không gọi SDK trực tiếp."""
    from types import SimpleNamespace

    spy = mocker.patch.object(
        mapping.gateway, "complete",
        mocker.AsyncMock(return_value='{"topic_id": 5, "muc_do": "trung_binh"}'),
    )
    topics = [SimpleNamespace(id=5, mach_noi_dung="Số", don_vi_kien_thuc="Số nguyên tố")]
    out = await mapping.suggest_mapping("Đề KT chương 1", ["2 là số nguyên tố?"], topics)

    assert out == (5, "trung_binh")
    assert spy.call_args.args[0] == "itest_map"  # đúng task -> đúng tier + trace

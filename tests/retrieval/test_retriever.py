from qdrant_client.models import FieldCondition

from app.retrieval import retriever


def _conditions(flt):
    return {c.key: c.match.value for c in flt.must if isinstance(c, FieldCondition)}


def test_build_filter_bat_buoc_mon_va_khoi():
    flt = retriever._build_filter(mon="toan", khoi="lop_6")
    assert _conditions(flt) == {"mon": "toan", "khoi": "lop_6"}


def test_build_filter_them_dieu_kien_tuy_chon():
    flt = retriever._build_filter(
        mon="toan", khoi="lop_6", sach="cung_kham_pha_tap_1", chuong_so=1,
        loai_noi_dung="vi_du",
    )
    assert _conditions(flt) == {
        "mon": "toan", "khoi": "lop_6", "sach": "cung_kham_pha_tap_1",
        "chuong_so": 1, "loai_noi_dung": "vi_du",
    }


async def test_retrieve_embed_query_va_tra_ve_chunk_sap_theo_diem(mocker):
    mocker.patch("app.retrieval.retriever.gateway.embed",
                 mocker.AsyncMock(return_value=[[0.1, 0.2, 0.3]]))
    hit1 = mocker.Mock(score=0.9, payload={"content": "A", "chuong_so": 1, "bai_so": 1,
                                           "page_no": 6, "loai_noi_dung": "ly_thuyet", "nguon": "n1"})
    hit2 = mocker.Mock(score=0.7, payload={"content": "B", "chuong_so": 1, "bai_so": 1,
                                           "page_no": 7, "loai_noi_dung": "vi_du", "nguon": "n2"})
    fake_client = mocker.Mock()
    fake_client.query_points = mocker.AsyncMock(return_value=mocker.Mock(points=[hit1, hit2]))
    mocker.patch("app.retrieval.retriever._client", return_value=fake_client)

    results = await retriever.retrieve("tập hợp là gì", mon="toan", khoi="lop_6", top_k=5)

    assert [r.content for r in results] == ["A", "B"]
    assert results[0].score == 0.9
    assert results[0].page_no == 6
    # query embed đúng câu hỏi
    retriever.gateway.embed.assert_awaited_once_with(["tập hợp là gì"])
    # gọi Qdrant với top_k
    assert fake_client.query_points.call_args.kwargs["limit"] == 5


async def test_retrieve_loc_diem_duoi_nguong(mocker):
    mocker.patch("app.retrieval.retriever.gateway.embed",
                 mocker.AsyncMock(return_value=[[0.1]]))
    hit_cao = mocker.Mock(score=0.8, payload={"content": "cao", "chuong_so": 1, "bai_so": 1,
                                              "page_no": 6, "loai_noi_dung": "ly_thuyet", "nguon": "n"})
    hit_thap = mocker.Mock(score=0.2, payload={"content": "thấp", "chuong_so": 1, "bai_so": 1,
                                               "page_no": 6, "loai_noi_dung": "ly_thuyet", "nguon": "n"})
    fake_client = mocker.Mock()
    fake_client.query_points = mocker.AsyncMock(return_value=mocker.Mock(points=[hit_cao, hit_thap]))
    mocker.patch("app.retrieval.retriever._client", return_value=fake_client)

    results = await retriever.retrieve("x", mon="toan", khoi="lop_6", score_threshold=0.5)

    assert [r.content for r in results] == ["cao"]  # loại chunk điểm 0.2

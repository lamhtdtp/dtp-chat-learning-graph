from app.ingestion import qdrant_store
from app.ingestion.chunking import Chunk, ChunkMetadata


def _chunk(page_no: int, content: str) -> Chunk:
    return Chunk(
        content=content,
        metadata=ChunkMetadata(
            mon="toan", khoi="lop_6", sach="cung_kham_pha_tap_1", tap=1,
            chuong_so=1, chuong_ten="Số tự nhiên", bai_so=1, bai_ten="TẬP HỢP",
            page_no=page_no, nguon="...", loai_noi_dung="ly_thuyet",
        ),
    )


def test_point_id_on_dinh_va_khac_nhau_theo_vi_tri():
    a1 = qdrant_store._point_id("sach_x", 6, 0)
    a2 = qdrant_store._point_id("sach_x", 6, 0)
    assert a1 == a2  # ổn định -> ingest lại ghi đè, không nhân bản
    assert a1 != qdrant_store._point_id("sach_x", 6, 1)  # khác index
    assert a1 != qdrant_store._point_id("sach_x", 7, 0)  # khác trang
    assert a1 != qdrant_store._point_id("sach_y", 6, 0)  # khác sách


async def test_upsert_chunks_rong_khong_goi_qdrant(mocker):
    spy = mocker.patch("app.ingestion.qdrant_store._client")
    n = await qdrant_store.upsert_chunks([])
    assert n == 0
    spy.assert_not_called()


async def test_upsert_chunks_id_theo_tung_trang(mocker):
    mocker.patch("app.ingestion.qdrant_store.gateway.embed",
                 mocker.AsyncMock(return_value=[[0.0] * 4, [0.0] * 4, [0.0] * 4]))
    fake_client = mocker.Mock()
    fake_client.upsert = mocker.AsyncMock()
    mocker.patch("app.ingestion.qdrant_store.ensure_collection", mocker.AsyncMock())

    chunks = [_chunk(6, "a"), _chunk(6, "b"), _chunk(7, "c")]
    n = await qdrant_store.upsert_chunks(chunks, client=fake_client)

    assert n == 3
    points = fake_client.upsert.call_args.kwargs["points"]
    # trang 6 có 2 chunk (index 0,1), trang 7 có 1 (index 0) — id khớp công thức
    assert points[0].id == qdrant_store._point_id("cung_kham_pha_tap_1", 6, 0)
    assert points[1].id == qdrant_store._point_id("cung_kham_pha_tap_1", 6, 1)
    assert points[2].id == qdrant_store._point_id("cung_kham_pha_tap_1", 7, 0)
    assert points[0].payload["content"] == "a"
    assert points[0].payload["loai_noi_dung"] == "ly_thuyet"

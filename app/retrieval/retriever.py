"""Retriever đọc Qdrant, LUÔN filter theo metadata (mon/khoi tối thiểu).

Retrieve không filter trên tập nhiều sách sẽ trả nhiễu chéo lớp/chương (xem
skill rag-orchestration Phần B). Query embed đi qua app.llm.gateway để cùng
model embedding với lúc ingest — lệch model embedding giữa index và query làm
hỏng retrieval.
"""

from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from app.config import settings
from app.llm import gateway

# Alias `mon`: dữ liệu OCR/ingest có thể gắn "tieng_anh" HOẶC "anh" (lịch sử ingest
# không nhất quán). Filter theo CẢ NHÓM để retrieve không lệch chỉ vì tên môn.
_MON_ALIASES: dict[str, list[str]] = {
    "tieng_anh": ["tieng_anh", "anh"],
    "anh": ["tieng_anh", "anh"],
}


class RetrievedChunk(BaseModel):
    content: str
    score: float
    chuong_so: int | None
    bai_so: int | None
    page_no: int
    tap: int | None  # để mở ảnh trang gốc (data/books/.../{tap}/{page}.png)
    loai_noi_dung: str
    nguon: str


def _client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.qdrant_url)


def _build_filter(
    *,
    mon: str,
    khoi: str,
    sach: str | None = None,
    chuong_so: int | None = None,
    loai_noi_dung: str | None = None,
) -> Filter:
    aliases = _MON_ALIASES.get(mon)
    mon_cond = (
        FieldCondition(key="mon", match=MatchAny(any=aliases))
        if aliases
        else FieldCondition(key="mon", match=MatchValue(value=mon))
    )
    conditions = [
        mon_cond,
        FieldCondition(key="khoi", match=MatchValue(value=khoi)),
    ]
    if sach is not None:
        conditions.append(FieldCondition(key="sach", match=MatchValue(value=sach)))
    if chuong_so is not None:
        conditions.append(FieldCondition(key="chuong_so", match=MatchValue(value=chuong_so)))
    if loai_noi_dung is not None:
        conditions.append(FieldCondition(key="loai_noi_dung", match=MatchValue(value=loai_noi_dung)))
    return Filter(must=conditions)


async def retrieve(
    query: str,
    *,
    mon: str,
    khoi: str,
    sach: str | None = None,
    chuong_so: int | None = None,
    loai_noi_dung: str | None = None,
    top_k: int = 5,
    score_threshold: float | None = None,
) -> list[RetrievedChunk]:
    (query_vector,) = await gateway.embed([query])

    client = _client()
    response = await client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=_build_filter(
            mon=mon, khoi=khoi, sach=sach, chuong_so=chuong_so, loai_noi_dung=loai_noi_dung
        ),
        limit=top_k,
        with_payload=True,
    )

    results: list[RetrievedChunk] = []
    for point in response.points:
        if score_threshold is not None and point.score < score_threshold:
            continue
        p = point.payload
        results.append(
            RetrievedChunk(
                content=p["content"],
                score=point.score,
                chuong_so=p.get("chuong_so"),
                bai_so=p.get("bai_so"),
                page_no=p["page_no"],
                tap=p.get("tap"),
                loai_noi_dung=p["loai_noi_dung"],
                nguon=p["nguon"],
            )
        )
    return results

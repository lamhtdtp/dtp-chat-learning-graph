"""Ghi chunk SGK (kèm embedding + metadata) vào Qdrant.

Chỉ SGK vào Qdrant — ma trận là dữ liệu cấu trúc, ở Postgres, KHÔNG vào đây
(nguyên tắc số 1 skill data-ingestion). Metadata đi cùng point làm payload để
retriever filter theo mon/khoi/sach/chuong/loai_noi_dung (xem retrieval sau).
"""

import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings
from app.ingestion.chunking import Chunk
from app.llm import gateway

# gemini-embedding-001 trả vector 3072 chiều (đã verify thật, xem gateway).
_EMBEDDING_DIM = 3072
# Namespace cố định để sinh point id ổn định theo (sach, page, thứ tự chunk) —
# ingest lại cùng trang sẽ ghi đè đúng point cũ, không tạo bản trùng.
_ID_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def _client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.qdrant_url)


def _point_id(sach: str, page_no: int, index: int) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, f"{sach}:{page_no}:{index}"))


async def ensure_collection(client: AsyncQdrantClient | None = None) -> None:
    client = client or _client()
    if not await client.collection_exists(settings.qdrant_collection):
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=_EMBEDDING_DIM, distance=Distance.COSINE),
        )


async def upsert_chunks(chunks: list[Chunk], client: AsyncQdrantClient | None = None) -> int:
    """Embed rồi upsert. Trả về số chunk đã ghi. Point id ổn định theo
    (sach, page, index) nên chạy lại idempotent (ghi đè, không nhân bản)."""
    if not chunks:
        return 0

    client = client or _client()
    await ensure_collection(client)

    vectors = await gateway.embed([c.content for c in chunks])

    # index tính theo TỪNG (sach, page) để id ổn định dù gọi per-page hay cả
    # sách một lượt — ingest lại ghi đè đúng point, không nhân bản.
    seen: dict[tuple[str, int], int] = {}
    points = []
    for chunk, vector in zip(chunks, vectors):
        key = (chunk.metadata.sach, chunk.metadata.page_no)
        idx = seen.get(key, 0)
        seen[key] = idx + 1
        points.append(
            PointStruct(
                id=_point_id(chunk.metadata.sach, chunk.metadata.page_no, idx),
                vector=vector,
                payload={"content": chunk.content, **chunk.metadata.model_dump()},
            )
        )
    await client.upsert(collection_name=settings.qdrant_collection, points=points)
    return len(points)

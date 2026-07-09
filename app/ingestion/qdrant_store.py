"""Ghi chunk SGK (kèm embedding + metadata) vào Qdrant.

Chỉ SGK vào Qdrant — ma trận là dữ liệu cấu trúc, ở Postgres, KHÔNG vào đây
(nguyên tắc số 1 skill data-ingestion). Metadata đi cùng point làm payload để
retriever filter theo mon/khoi/sach/chuong/loai_noi_dung (xem retrieval sau).
"""

import asyncio
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings
from app.ingestion.chunking import Chunk
from app.llm import gateway

# Vector 3072 chiều — trùng cho cả openai/text-embedding-3-large (đang dùng) lẫn
# gemini/gemini-embedding-001 (đã verify thật). Đổi model embedding KHÁC dim thì
# phải tạo lại collection.
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

    # Embed TRƯỚC (gọi VNGCloud, không liên quan Qdrant) — chỉ 1 lần, retry
    # phía dưới không embed lại.
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

    # Ghi Qdrant có RETRY: local Docker Qdrant hay bị restart chớp nhoáng ->
    # connection refused; retry (backoff) để không mất công embed lại. Chia
    # batch nhỏ để mỗi lần ghi nhẹ, upsert idempotent nên retry an toàn.
    # Nếu caller không truyền client (production), mỗi lần thử tạo client MỚI
    # (kết nối cũ có thể chết sau restart); nếu truyền (test) thì dùng lại.
    def _c() -> AsyncQdrantClient:
        return client or _client()

    await _with_retry(lambda: ensure_collection(_c()))
    for i in range(0, len(points), 64):
        batch = points[i : i + 64]
        await _with_retry(
            lambda b=batch: _c().upsert(collection_name=settings.qdrant_collection, points=b)
        )
    return len(points)


async def _with_retry(op, attempts: int = 5, base_delay: float = 2.0):
    """Chạy 1 thao tác Qdrant, retry khi lỗi kết nối (Qdrant restart tạm thời)."""
    for attempt in range(attempts):
        try:
            return await op()
        except (ResponseHandlingException, ConnectionError, OSError):
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(base_delay * (attempt + 1))

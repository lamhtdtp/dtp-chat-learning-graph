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

# Vector 1024 chiều — baai/bge-m3 (dense). Trước là 3072 cho
# openai/text-embedding-3-large / gemini/gemini-embedding-001, nhưng provider đã
# bỏ model đó (404 "model is not found").
#
# ĐỔI MODEL EMBEDDING LUÔN PHẢI NẠP LẠI TOÀN BỘ, không chỉ khi lệch chiều: vector
# của hai model nằm ở hai không gian khác nhau nên cosine giữa chúng vô nghĩa.
# Lệch chiều thì Qdrant báo lỗi lúc upsert (còn dễ), CÙNG chiều mà khác model thì
# truy hồi thành rác trong IM LẶNG — đó là ca nguy hiểm hơn.
_EMBEDDING_DIM = 1024
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
        return

    # Collection đã tồn tại: chiều vector KHÔNG sửa được tại chỗ. Không chặn ở
    # đây thì đổi model lệch chiều sẽ nổ giữa lúc nạp, dưới dạng lỗi Qdrant khó
    # lần và có thể đã ghi dở nửa cuốn. Chặn TRƯỚC, nói rõ phải làm gì.
    info = await client.get_collection(settings.qdrant_collection)
    # Chỉ đọc được `.size` khi collection dùng MỘT vector không tên (đúng như
    # create_collection ở trên). Dạng nhiều vector có tên -> bỏ kiểm, không đoán.
    dim = getattr(info.config.params.vectors, "size", None)
    if dim is not None and dim != _EMBEDDING_DIM:
        raise RuntimeError(
            f"Collection {settings.qdrant_collection!r} đang là {dim} chiều nhưng "
            f"model {settings.embedding_model!r} sinh {_EMBEDDING_DIM} chiều.\n"
            "Chiều vector không đổi được tại chỗ — phải XOÁ collection rồi nạp lại "
            "toàn bộ SGK (dữ liệu vector sẽ mất, nội dung bài trong Postgres thì không):\n"
            f"  curl -X DELETE {settings.qdrant_url}/collections/{settings.qdrant_collection}\n"
            "rồi chạy lại ingest cho từng cuốn đã nạp."
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

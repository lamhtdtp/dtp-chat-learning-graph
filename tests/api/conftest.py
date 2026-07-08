import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session, engine
from app.main import app


@pytest_asyncio.fixture
async def client():
    """AsyncClient gọi app; get_session bị override sang 1 connection chạy trong
    transaction rồi rollback ở cuối — không để lại dữ liệu trong Postgres thật."""
    try:
        connection = await engine.connect()
    except OperationalError as exc:
        pytest.skip(f"Cần Postgres tại DATABASE_URL: {exc}")

    # begin() mở transaction ngoài; session dùng SAVEPOINT nên endpoint gọi
    # commit() chỉ release savepoint, transaction ngoài vẫn mở và bị rollback
    # ở cuối -> không dữ liệu nào lọt vào Postgres thật.
    trans = await connection.begin()
    session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")

    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        await session.close()
        await trans.rollback()
        await connection.close()

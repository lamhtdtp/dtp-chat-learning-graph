import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine


@pytest_asyncio.fixture
async def db_session():
    """Mỗi test dùng 1 connection riêng, rollback ở cuối — không để lại dữ
    liệu trong Postgres thật (dùng chung DB `chat_learning` với dev, không
    phải DB ephemeral riêng cho test). `connection.rollback()` dọn sạch được
    kể cả khi transaction đã bị Postgres abort do IntegrityError giữa chừng —
    không cần savepoint lồng nhau cho các test đơn giản ở đây."""
    try:
        connection = await engine.connect()
    except OperationalError as exc:
        pytest.skip(f"Cần Postgres tại DATABASE_URL đang chạy: {exc}")

    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await connection.rollback()
        await connection.close()

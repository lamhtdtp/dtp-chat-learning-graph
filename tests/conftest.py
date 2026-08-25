import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine


@pytest_asyncio.fixture
async def db_session():
    """Mỗi test dùng 1 connection riêng, rollback ở cuối — không để lại dữ
    liệu trong Postgres thật (dùng chung DB `chat_learning` với dev, không phải
    DB ephemeral riêng cho test).

    Transaction NGOÀI + join_transaction_mode="create_savepoint" (giống
    tests/api/conftest.py): có mã được test tự gọi `session.commit()` — job nạp
    sách phải commit sau MỖI trang, không thì UI đứng ở 0/149 suốt. Không có
    savepoint thì chính lần commit đó ghi thẳng vào DB dev và để lại rác
    (đã gặp thật: 15 job `ma_sach_test` nằm trong danh sách của CMS).
    """
    try:
        connection = await engine.connect()
    except OperationalError as exc:
        pytest.skip(f"Cần Postgres tại DATABASE_URL đang chạy: {exc}")

    trans = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False,
                           join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        await session.close()
        if trans.is_active:
            await trans.rollback()
        await connection.rollback()
        await connection.close()

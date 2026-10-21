import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session, engine
from app.main import app


@pytest_asyncio.fixture
async def session():
    """1 connection chạy trong transaction rồi rollback ở cuối — không để lại dữ
    liệu trong Postgres thật. Test có thể dùng trực tiếp để dựng dữ liệu (vd tạo
    admin)."""
    try:
        connection = await engine.connect()
    except OperationalError as exc:
        pytest.skip(f"Cần Postgres tại DATABASE_URL: {exc}")
    # begin() mở transaction ngoài; session dùng SAVEPOINT nên endpoint gọi
    # commit() chỉ release savepoint, transaction ngoài vẫn mở và bị rollback.
    trans = await connection.begin()
    sess = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield sess
    finally:
        await sess.close()
        await trans.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def client(session):
    """AsyncClient gọi app; get_session override sang cùng `session` của test."""
    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()


async def tao_tai_khoan(client, role: str = "hoc_sinh", ten: str = "An",
                        prefix: str = "u", mat_khau: str = "matkhau123"):
    """Tạo tài khoản trong test, trả `(email, headers)`.

    Vì sao: US-26 KB 38 cấm tự đăng ký vai khác học sinh qua `/auth/register`,
    nên giáo viên / chuyên gia / admin phải được tạo trực tiếp trong DB: đăng ký
    học sinh rồi đổi `role` (cùng cách `_make_admin` của test_admin). Dùng cùng
    `session` mà fixture `client` đã gắn vào app nên không cần truyền session.
    """
    from app.db.models import User
    from app.db.session import get_session

    email = f"{prefix}-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": mat_khau, "name": ten})
    assert r.status_code == 200, r.text
    if role != "hoc_sinh":
        gen = app.dependency_overrides[get_session]()
        sess = await gen.__anext__()
        u = await sess.scalar(select(User).where(User.email == email))
        u.role = role
        await sess.commit()
    return email, {"Authorization": f"Bearer {r.json()['token']}"}

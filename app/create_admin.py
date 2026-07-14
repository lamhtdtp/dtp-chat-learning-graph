"""Tạo hoặc nâng quyền tài khoản ADMIN (đăng ký thường không chọn được admin).

Dùng:
    python -m app.create_admin --email admin@dtp.vn --password '••••••' [--name 'Quản trị']
- Email chưa có  -> tạo user admin mới.
- Email đã có    -> nâng lên admin (và mở khoá nếu đang bị khoá).
"""
import argparse
import asyncio

from sqlalchemy import select

from app.api import security
from app.db.models import User
from app.db.session import async_session_factory


async def _run(email: str, password: str, name: str) -> None:
    async with async_session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, password_hash=security.hash_password(password),
                        name=name, role="admin", is_active=True)
            session.add(user)
            action = "Đã tạo admin mới"
        else:
            user.role = "admin"
            user.is_active = True
            if password:
                user.password_hash = security.hash_password(password)
            action = "Đã nâng quyền admin"
        await session.commit()
        print(f"{action}: {email} (id={user.id})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Tạo/nâng quyền admin")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--name", default="Quản trị viên")
    args = ap.parse_args()
    asyncio.run(_run(args.email, args.password, args.name))


if __name__ == "__main__":
    main()

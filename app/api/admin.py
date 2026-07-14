"""API quản trị (chỉ role=admin): quản lý user + tracking câu hỏi.

- GET  /admin/users                 — danh sách user + thống kê (phiên, câu hỏi, lượt hôm nay)
- GET  /admin/users/{id}/messages   — các câu hỏi user đó đã gửi (tracking)
- POST /admin/users/{id}/active      — khoá / mở tài khoản
- POST /admin/users/{id}/settings    — đổi vai trò / hạn mức chat/ngày

Admin tạo bằng CLI `python -m app.create_admin` (đăng ký thường KHÔNG chọn được
admin — chống tự nâng quyền).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import ChatSession, Message, User
from app.db.session import get_session
from app.llm import cache

router = APIRouter(prefix="/admin", tags=["admin"])

_ROLES = {"hoc_sinh", "giao_vien", "admin"}


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ quản trị viên mới được phép.")


async def _today_quota(user_id: int) -> int:
    key = f"chatquota:{user_id}:{datetime.now(timezone.utc):%Y%m%d}"
    try:
        v = await cache.get(key)
    except Exception:  # noqa: BLE001
        return 0
    return int(v) if v else 0


@router.get("/users")
async def list_users(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    _require_admin(user)
    # Đếm phiên + câu hỏi (role=user) mỗi user bằng subquery gộp -> tránh N+1.
    sc = (select(ChatSession.user_id, func.count().label("n"))
          .group_by(ChatSession.user_id).subquery())
    mc = (select(ChatSession.user_id, func.count().label("n"))
          .join(Message, Message.session_id == ChatSession.id)
          .where(Message.role == "user")
          .group_by(ChatSession.user_id).subquery())
    rows = await session.execute(
        select(User, sc.c.n, mc.c.n)
        .outerjoin(sc, sc.c.user_id == User.id)
        .outerjoin(mc, mc.c.user_id == User.id)
        .order_by(User.created_at.desc())
    )
    out = []
    for u, n_sessions, n_msgs in rows.all():
        out.append({
            "id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "is_active": u.is_active, "daily_limit_override": u.daily_limit_override,
            "created_at": u.created_at.isoformat(),
            "sessions": n_sessions or 0, "questions": n_msgs or 0,
            "today": await _today_quota(u.id),
        })
    return out


@router.get("/users/{user_id}/messages")
async def user_messages(
    user_id: int, limit: int = 100,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Các câu hỏi (role=user) của 1 user — mới nhất trước (tracking)."""
    _require_admin(user)
    rows = await session.execute(
        select(Message.content, Message.created_at, ChatSession.subject)
        .join(ChatSession, Message.session_id == ChatSession.id)
        .where(ChatSession.user_id == user_id, Message.role == "user")
        .order_by(Message.created_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    return [{"content": c, "created_at": t.isoformat(), "subject": s} for c, t, s in rows.all()]


class ActiveBody(BaseModel):
    active: bool


@router.post("/users/{user_id}/active")
async def set_active(
    user_id: int, body: ActiveBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_admin(user)
    if user_id == user.id and not body.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể tự khoá chính mình.")
    target = await session.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy user")
    target.is_active = body.active
    await session.commit()
    return {"id": user_id, "is_active": body.active}


class SettingsBody(BaseModel):
    role: str | None = None
    daily_limit: int | None = None   # None + clear=True -> xoá override (dùng mặc định)
    clear_limit: bool = False


@router.post("/users/{user_id}/settings")
async def set_settings(
    user_id: int, body: SettingsBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_admin(user)
    target = await session.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy user")
    if body.role is not None:
        if body.role not in _ROLES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vai trò không hợp lệ")
        if user_id == user.id and body.role != "admin":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không thể tự hạ quyền admin của mình.")
        target.role = body.role
    if body.clear_limit:
        target.daily_limit_override = None
    elif body.daily_limit is not None:
        target.daily_limit_override = max(0, body.daily_limit)
    role_out, limit_out = target.role, target.daily_limit_override  # đọc TRƯỚC commit
    await session.commit()
    return {"id": user_id, "role": role_out, "daily_limit_override": limit_out}

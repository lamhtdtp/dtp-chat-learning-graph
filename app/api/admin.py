"""API quản trị (chỉ role=admin): quản lý user + theo dõi tiến độ học.

- GET  /admin/users                 — danh sách user + tiến độ (đơn vị đạt / đang học)
- POST /admin/users/{id}/active      — khoá / mở tài khoản
- POST /admin/users/{id}/settings    — đổi vai trò / hạn mức riêng

Admin tạo bằng CLI `python -m app.create_admin` (đăng ký thường KHÔNG chọn được
admin — chống tự nâng quyền). Chat/RAG đã bỏ (P5) nên không còn thống kê "lượt hỏi".
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import StudentProgress, User
from app.db.session import get_session

router = APIRouter(prefix="/admin", tags=["admin"])

_ROLES = {"hoc_sinh", "giao_vien", "admin"}


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ quản trị viên mới được phép.")


@router.get("/users")
async def list_users(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    _require_admin(user)
    # Đếm tiến độ mỗi user bằng subquery gộp (tránh N+1): đơn vị Đạt / Đang học.
    dat = (select(StudentProgress.user_id, func.count().label("n"))
           .where(StudentProgress.trang_thai == "dat")
           .group_by(StudentProgress.user_id).subquery())
    dang = (select(StudentProgress.user_id, func.count().label("n"))
            .where(StudentProgress.trang_thai == "dang")
            .group_by(StudentProgress.user_id).subquery())
    rows = await session.execute(
        select(User, dat.c.n, dang.c.n)
        .outerjoin(dat, dat.c.user_id == User.id)
        .outerjoin(dang, dang.c.user_id == User.id)
        .order_by(User.created_at.desc())
    )
    out = []
    for u, n_dat, n_dang in rows.all():
        out.append({
            "id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "is_active": u.is_active, "daily_limit_override": u.daily_limit_override,
            "created_at": u.created_at.isoformat(),
            "hoan_thanh": n_dat or 0, "dang_hoc": n_dang or 0,
        })
    return out


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

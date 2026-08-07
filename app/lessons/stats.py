"""Gamification học sinh: cộng XP, tính chuỗi ngày học (streak), điểm tuần.

Gọi khi HS có hoạt động học (nộp quiz đạt, đánh dấu hoàn thành). Streak tăng khi
học vào ngày MỚI liền kề; đứt (về 1) nếu cách > 1 ngày. Điểm tuần reset đầu tuần
(thứ Hai). Tách khỏi StudentProgress để không đụng logic tiến độ.
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StudentStats


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def get_or_create(session: AsyncSession, user_id: int) -> StudentStats:
    row = await session.scalar(select(StudentStats).filter_by(user_id=user_id))
    if row is None:
        row = StudentStats(user_id=user_id)
        session.add(row)
        await session.flush()
    return row


async def award(session: AsyncSession, user_id: int, points: int, *, today: date | None = None) -> StudentStats:
    """Cộng `points` XP cho user + cập nhật streak/điểm tuần theo `today`.
    KHÔNG commit — caller commit chung với thao tác gốc."""
    today = today or date.today()
    s = await get_or_create(session, user_id)

    # Streak: ngày mới liền kề -> +1; cùng ngày -> giữ; cách quãng -> về 1.
    if s.last_study is None or s.last_study < today - timedelta(days=1):
        s.streak_days = 1
    elif s.last_study == today - timedelta(days=1):
        s.streak_days = (s.streak_days or 0) + 1
    # last_study == today: streak giữ nguyên
    s.last_study = today

    # Điểm tuần: reset khi sang tuần mới (mốc thứ Hai).
    mon = _monday(today)
    if s.week_start != mon:
        s.week_start = mon
        s.week_points = 0
    s.week_points = (s.week_points or 0) + points

    s.xp_total = (s.xp_total or 0) + points
    return s

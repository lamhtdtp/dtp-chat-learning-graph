"""API quản trị: quản lý user + theo dõi tiến độ và kết quả học.

- GET  /admin/users                  — danh sách user + tiến độ (đơn vị đạt / đang học)  [admin]
- POST /admin/users/{id}/active      — khoá / mở tài khoản                                [admin]
- POST /admin/users/{id}/settings    — đổi vai trò / hạn mức riêng                        [admin]
- GET  /admin/users/{id}/result      — kết quả Kiểm tra nhanh từng lần       [giáo viên + admin]
- POST /admin/users                  — tạo tài khoản chuyên gia / quản trị            [admin]

/auth/register KHÔNG cho chọn role=admin (chống tự nâng quyền); tài khoản chuyên
gia và quản trị tạo qua POST /admin/users — hoặc CLI `python -m app.create_admin`
cho admin ĐẦU TIÊN, khi chưa có ai để đăng nhập.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import security
from app.api.deps import get_current_user
from app.db.models import CurriculumTopic, QuizAttempt, StudentProgress, TopicContent, User
from app.db.session import get_session

router = APIRouter(prefix="/admin", tags=["admin"])

_ROLES = {"hoc_sinh", "giao_vien", "chuyen_gia", "admin"}
# Vai trò làm việc trong CMS (không phải tài khoản học).
_NOI_BO = {"chuyen_gia", "giao_vien", "admin"}


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ quản trị viên mới được phép.")


def _require_author(user: User) -> None:
    """Xem kết quả học tập: GIÁO VIÊN cũng được, không riêng quản trị — dạy lớp
    thì phải xem được điểm. Sửa vai trò / khoá tài khoản vẫn chỉ admin."""
    if user.role not in _NOI_BO:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ tài khoản nội bộ mới được xem.")


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


@router.get("/users/{user_id}/result")
async def student_result(
    user_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Kết quả làm Kiểm tra nhanh của 1 học sinh: từng lần nộp + tổng hợp theo đơn vị.

    Đọc quiz_attempts (ghi từ /lessons/quiz/submit). Bảng chỉ có dữ liệu TỪ KHI
    triển khai — các lượt làm trước đó không được lưu, không dựng lại được.
    """
    _require_author(user)
    hs = await session.get(User, user_id)
    if hs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy học sinh")
    # Chỉ HỌC SINH mới có kết quả học tập. Giáo viên/quản trị có làm thử quiz thì
    # cũng không phải dữ liệu đánh giá — trả 400 rõ ràng thay vì bảng rỗng khó hiểu.
    if hs.role != "hoc_sinh":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Chỉ xem được kết quả của tài khoản học sinh.")

    rows = (await session.execute(
        select(QuizAttempt, CurriculumTopic.don_vi_kien_thuc, CurriculumTopic.mach_noi_dung)
        .join(CurriculumTopic, CurriculumTopic.id == QuizAttempt.topic_id)
        .where(QuizAttempt.user_id == user_id)
        # id DESC phá hoà: Postgres now() là mốc BẮT ĐẦU transaction nên hai lần
        # nộp sát nhau có created_at y hệt -> thiếu nó thì "gần nhất" sắp tuỳ ý.
        .order_by(QuizAttempt.created_at.desc(), QuizAttempt.id.desc())
    )).all()

    lan = [{
        "topic_id": a.topic_id, "ten": (dv or "").strip(), "mach": (mach or "").strip(),
        "diem": a.diem, "tong": a.tong, "dat": a.dat, "nguon": a.nguon or "nhanh",
        "phan_tram": round(100 * a.diem / a.tong) if a.tong else 0,
        "luc": a.created_at.isoformat(),
    } for a, dv, mach in rows]
    # Trung bình & "số lần làm" CHỈ tính Kiểm tra nhanh: một lần nộp đề ôn tập
    # sinh nhiều mảnh 1/4 cho từng bài, trộn vào là đếm sai số lần và kéo lệch
    # điểm trung bình.
    nhanh = [x for x in lan if x["nguon"] == "nhanh"]

    # Trạng thái đơn vị lấy từ student_progress — ĐÚNG nguồn mà phía học sinh
    # hiển thị. Trước đây suy từ các lượt quiz nên bài học sinh bấm "Đã hoàn
    # thành" (không làm quiz) KHÔNG hề xuất hiện ở đây: giáo viên mở CMS ra thấy
    # trống và tưởng em chưa học.
    prog_rows = (await session.execute(
        select(StudentProgress, CurriculumTopic.don_vi_kien_thuc,
               CurriculumTopic.mach_noi_dung)
        .join(CurriculumTopic, CurriculumTopic.id == StudentProgress.topic_id)
        .where(StudentProgress.user_id == user_id))).all()
    trang_thai = {p.topic_id: p.trang_thai for p, _, _ in prog_rows}

    theo_dv: dict[int, dict] = {}

    def _o(topic_id: int, ten: str, mach: str) -> dict:
        return theo_dv.setdefault(topic_id, {
            "topic_id": topic_id, "ten": (ten or "").strip(), "mach": (mach or "").strip(),
            "trang_thai": trang_thai.get(topic_id, "chua"),
            "so_lan": 0, "so_lan_on_tap": 0, "tot_nhat": None, "gan_nhat": None,
        })

    # Mọi đơn vị HS đã có trạng thái, kể cả chưa làm quiz lần nào.
    for p, dv, mach in prog_rows:
        _o(p.topic_id, dv, mach)
    for x in lan:
        g = _o(x["topic_id"], x["ten"], x["mach"])
        if x["nguon"] == "on_tap":
            g["so_lan_on_tap"] += 1
            continue
        if g["gan_nhat"] is None:      # `lan` sắp mới -> cũ, gặp đầu là gần nhất
            g["gan_nhat"] = x["phan_tram"]
        g["so_lan"] += 1
        g["tot_nhat"] = max(g["tot_nhat"] or 0, x["phan_tram"])

    return {
        "hoc_sinh": {"id": hs.id, "name": hs.name, "email": hs.email},
        # Khớp con số phía học sinh nhìn thấy trên vòng tiến độ.
        "so_dat": sum(1 for t in trang_thai.values() if t == "dat"),
        "so_dang": sum(1 for t in trang_thai.values() if t == "dang"),
        "tong_lan": len(nhanh),
        "tong_lan_on_tap": len(lan) - len(nhanh),
        "so_lan_dat": sum(1 for x in nhanh if x["dat"]),
        "diem_tb": round(sum(x["phan_tram"] for x in nhanh) / len(nhanh)) if nhanh else 0,
        # Sắp theo trạng thái (đạt trước) rồi tới số lần làm — giáo viên tìm em
        # yếu ở đâu, không phải tìm ai làm nhiều nhất.
        "theo_don_vi": sorted(theo_dv.values(),
                              key=lambda g: ({"dat": 0, "dang": 1, "chua": 2}[g["trang_thai"]],
                                             -g["so_lan"])),
        "lan": lan[:50],   # đủ để xem lại, không đổ cả nghìn dòng về client
    }


class CreateUserBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)
    role: str          # chuyen_gia | giao_vien | admin — KHÔNG tạo học sinh ở đây


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_staff(
    body: CreateUserBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Tạo tài khoản CHUYÊN GIA (giáo viên) hoặc QUẢN TRỊ. Chỉ quản trị được gọi.

    /auth/register cố ý KHÔNG cho chọn role=admin (chống tự nâng quyền), nên trước
    đây tạo admin phải chạy CLI trên server. Đường này thay thế cho việc đó, và
    quyền tạo nằm trong tay người đã là admin.

    Không tạo học sinh ở đây: học sinh tự đăng ký qua /auth/register.
    """
    _require_admin(user)
    if body.role not in _NOI_BO:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Chỉ tạo được tài khoản nội bộ (chuyên gia / giáo viên / quản trị).")
    if await session.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được đăng ký")

    moi = User(email=body.email, password_hash=security.hash_password(body.password),
               name=body.name.strip(), role=body.role)
    session.add(moi)
    await session.commit()
    await session.refresh(moi)
    return {"id": moi.id, "email": moi.email, "name": moi.name, "role": moi.role}


@router.get("/overview")
async def overview(
    ngay: int = 14,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Số liệu học tập cho trang Tổng quan CMS.

    Ba lớp, mỗi lớp trả lời một câu khác nhau:
      - `tong`      : quy mô đang diễn ra (tile số lớn)
      - `hoat_dong` : nhịp học `ngay` ngày gần nhất (đường)
      - `kho_nhat`  : đơn vị học sinh trượt nhiều nhất (cột xếp hạng)

    `kho_nhat` là thứ đáng giá nhất với người biên soạn: nó chỉ thẳng nội dung
    nào cần viết lại, thay vì chỉ nói "học sinh yếu".
    """
    _require_author(user)
    ngay = max(1, min(ngay, 90))
    tu = date.today() - timedelta(days=ngay - 1)

    tong_lan, hs_hd, dat = (await session.execute(
        select(func.count(QuizAttempt.id),
               func.count(func.distinct(QuizAttempt.user_id)),
               func.count(QuizAttempt.id).filter(QuizAttempt.dat))
    )).one()

    # Nhịp theo ngày. Ngày KHÔNG có lượt nào sẽ thiếu trong kết quả SQL -> phải
    # bơm 0 vào, nếu không đường biểu đồ nối tắt qua khoảng trống và trông như
    # ngày đó vẫn có hoạt động.
    rows = (await session.execute(
        select(func.date(QuizAttempt.created_at).label("ngay"), func.count(QuizAttempt.id))
        .where(func.date(QuizAttempt.created_at) >= tu)
        .group_by("ngay")
    )).all()
    theo_ngay = {str(d): n for d, n in rows}
    hoat_dong = [{"ngay": str(tu + timedelta(days=i)),
                  "so_lan": theo_ngay.get(str(tu + timedelta(days=i)), 0)}
                 for i in range(ngay)]

    # Đơn vị đuối nhất. Ngưỡng tối thiểu để 1 lượt trượt lẻ không nhảy lên đầu
    # bảng với "100% trượt".
    toi_thieu = 3
    kq = (await session.execute(
        select(CurriculumTopic.id, CurriculumTopic.don_vi_kien_thuc, CurriculumTopic.mach_noi_dung,
               func.count(QuizAttempt.id).label("n"),
               func.count(QuizAttempt.id).filter(~QuizAttempt.dat).label("truot"))
        .join(QuizAttempt, QuizAttempt.topic_id == CurriculumTopic.id)
        .group_by(CurriculumTopic.id, CurriculumTopic.don_vi_kien_thuc, CurriculumTopic.mach_noi_dung)
        .having(func.count(QuizAttempt.id) >= toi_thieu)
    )).all()
    kho_nhat = sorted(
        ({"topic_id": tid, "ten": (dv or "").strip(), "mach": (mach or "").strip(),
          "so_lan": n, "ty_le_truot": round(100 * truot / n)} for tid, dv, mach, n, truot in kq),
        key=lambda x: (-x["ty_le_truot"], -x["so_lan"]),
    )[:6]

    # Phân bố điểm: tỉ lệ đạt trung bình che mất hình dạng lớp học. "Cả lớp lơ
    # lửng 60%" và "một nửa giỏi một nửa mất gốc" cùng ra ~60% nhưng cần can
    # thiệp khác hẳn nhau. Gom về 5 khoảng 20%.
    pct = func.round(100.0 * QuizAttempt.diem / func.nullif(QuizAttempt.tong, 0))
    buckets = {int(k): v for k, v in (await session.execute(
        select(func.least(func.floor(pct / 20), 4).label("b"), func.count()).group_by("b")
    )).all() if k is not None}
    nhan = ["0–19%", "20–39%", "40–59%", "60–79%", "80–100%"]
    phan_bo = [{"khoang": nhan[i], "so_lan": buckets.get(i, 0), "dat": i >= 3} for i in range(5)]

    # Theo mạch nội dung: chỉ ra MẢNG kiến thức yếu, không phải từng bài lẻ.
    mach_rows = (await session.execute(
        select(CurriculumTopic.mach_noi_dung,
               func.count(QuizAttempt.id).label("n"),
               func.count(QuizAttempt.id).filter(QuizAttempt.dat).label("d"))
        .join(QuizAttempt, QuizAttempt.topic_id == CurriculumTopic.id)
        .group_by(CurriculumTopic.mach_noi_dung)
    )).all()
    theo_mach = sorted(
        ({"mach": (m or "").strip(), "so_lan": n, "ty_le_dat": round(100 * d / n)} for m, n, d in mach_rows),
        key=lambda x: x["ty_le_dat"],
    )

    # Phễu: chỗ học sinh rơi rụng. LƯU Ý bước "mở bài" KHÔNG có — hệ thống chưa
    # log lượt mở, nên phễu bắt đầu từ "có tài khoản". Đặt bước không đo được vào
    # đây sẽ là con số bịa.
    tong_hs = await session.scalar(
        select(func.count()).select_from(User).where(User.role == "hoc_sinh")) or 0
    hs_dat = await session.scalar(
        select(func.count(func.distinct(QuizAttempt.user_id))).where(QuizAttempt.dat)) or 0
    pheu = [
        {"buoc": "Có tài khoản học sinh", "so": tong_hs},
        {"buoc": "Đã làm ít nhất 1 bài", "so": hs_hd},
        {"buoc": "Đã đạt ít nhất 1 bài", "so": hs_dat},
    ]

    # Đối trọng của "trượt nhiều nhất": nội dung đã xuất bản mà chưa ai đụng tới.
    da_lam = select(QuizAttempt.topic_id).distinct().scalar_subquery()
    chua_hoc_rows = (await session.execute(
        select(CurriculumTopic.id, CurriculumTopic.don_vi_kien_thuc, CurriculumTopic.mach_noi_dung)
        .join(TopicContent, TopicContent.topic_id == CurriculumTopic.id)
        .where(TopicContent.trang_thai == "published", CurriculumTopic.id.not_in(da_lam))
        .order_by(CurriculumTopic.order_index)
    )).all()
    chua_hoc = [{"topic_id": i, "ten": (dv or "").strip(), "mach": (m or "").strip()}
                for i, dv, m in chua_hoc_rows]

    return {
        "tong": {"luot_lam": tong_lan, "hoc_sinh": hs_hd,
                 "ty_le_dat": round(100 * dat / tong_lan) if tong_lan else 0},
        "hoat_dong": hoat_dong,
        "kho_nhat": kho_nhat,
        "toi_thieu_luot": toi_thieu,
        "phan_bo": phan_bo,
        "theo_mach": theo_mach,
        "pheu": pheu,
        "chua_hoc": chua_hoc[:8],
        "chua_hoc_tong": len(chua_hoc),
    }

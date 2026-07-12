"""POST /exam/generate — sinh đề kiểm tra theo ma trận. CHỈ giáo viên.

Đề đi qua endpoint riêng (không qua /chat) vì luồng sinh đề là graph có vòng
lặp exam_gen<->check, khác hẳn hội thoại tuyến tính (xem full-system-spec mục
7, 11).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_session
from app.exam import service
from app.llm.gateway import LLMUnavailable

router = APIRouter(prefix="/exam", tags=["exam"])


# Môn cho phép sinh đề = môn ĐÃ nạp ma trận (Subject.name). Thêm môn = thêm dòng.
_MON_HOP_LE = {"Toán", "Tiếng Anh"}


class ExamRequest(BaseModel):
    hoc_ky: str = Field(pattern="^(hk1|hk2)$")
    tong_so_cau: int = Field(ge=1, le=50)
    mon: str = "Toán"


class PracticeRequest(BaseModel):
    # Đề NGẮN cho học sinh tự luyện — cùng ma trận, ít câu, giới hạn nhỏ.
    hoc_ky: str = Field(default="hk1", pattern="^(hk1|hk2)$")
    tong_so_cau: int = Field(default=5, ge=3, le=12)
    mon: str = "Toán"


class CauHoiOut(BaseModel):
    muc_do: str
    noi_dung: str
    dap_an: str
    loi_giai: str


class ExamResponse(BaseModel):
    hoc_ky: str
    mon: str = "Toán"
    tong_so_cau: int
    chi_tieu: dict[str, int]
    ti_le_muc_do: dict[str, float]
    mach_noi_dung: list[str]
    cau_hoi: list[CauHoiOut]
    canh_bao: str | None = None


def _require_teacher(user: User) -> None:
    if user.role != "giao_vien":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ giáo viên được sinh đề")


async def _sinh_de_or_http(session: AsyncSession, *, mon: str, hoc_ky: str, tong_so_cau: int) -> dict:
    """Gọi service.sinh_de + map lỗi sang HTTP (dùng chung cho giáo viên & luyện tập)."""
    if mon not in _MON_HOP_LE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Môn không hợp lệ: {mon!r}")
    try:
        result = await service.sinh_de(session, mon=mon, hoc_ky=hoc_ky, tong_so_cau=tong_so_cau)
    except service.BlueprintNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except LLMUnavailable:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Hệ thống AI đang quá tải, thử lại sau ít phút nhé.",
        )
    result["mon"] = mon
    return result


@router.post("/generate", response_model=ExamResponse)
async def generate_exam(
    body: ExamRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ExamResponse:
    _require_teacher(user)
    result = await _sinh_de_or_http(session, mon=body.mon, hoc_ky=body.hoc_ky, tong_so_cau=body.tong_so_cau)
    return ExamResponse(**result)


@router.post("/practice", response_model=ExamResponse)
async def generate_practice(
    body: PracticeRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ExamResponse:
    """Học sinh 'Tạo một đề ngắn luyện tập' — sinh đề NGẮN bám ĐÚNG ma trận đặc
    tả (như luồng của giáo viên), KHÔNG cần quyền giáo viên."""
    result = await _sinh_de_or_http(session, mon=body.mon, hoc_ky=body.hoc_ky, tong_so_cau=body.tong_so_cau)
    return ExamResponse(**result)

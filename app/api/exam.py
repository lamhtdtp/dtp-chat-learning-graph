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


class ExamRequest(BaseModel):
    hoc_ky: str = Field(pattern="^(hk1|hk2)$")
    tong_so_cau: int = Field(ge=1, le=50)


class CauHoiOut(BaseModel):
    muc_do: str
    noi_dung: str
    dap_an: str
    loi_giai: str


class ExamResponse(BaseModel):
    hoc_ky: str
    tong_so_cau: int
    chi_tieu: dict[str, int]
    ti_le_muc_do: dict[str, float]
    mach_noi_dung: list[str]
    cau_hoi: list[CauHoiOut]
    canh_bao: str | None = None


def _require_teacher(user: User) -> None:
    if user.role != "giao_vien":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ giáo viên được sinh đề")


@router.post("/generate", response_model=ExamResponse)
async def generate_exam(
    body: ExamRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ExamResponse:
    _require_teacher(user)
    try:
        result = await service.sinh_de(
            session, hoc_ky=body.hoc_ky, tong_so_cau=body.tong_so_cau
        )
    except service.BlueprintNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except LLMUnavailable:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Hệ thống AI đang quá tải, thầy/cô thử lại sau ít phút nhé.",
        )
    return ExamResponse(**result)

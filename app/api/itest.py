"""API Itest (EPIC-10): gợi ý câu theo blueprint, trộn Itest + AI, và quản trị
(đồng bộ read-only, duyệt ánh xạ taxonomy).

Suggest/assemble mở cho học sinh (luồng luyện tập song song đề tự sinh SGK).
Đồng bộ + duyệt ánh xạ chỉ cho giáo viên/quản trị. Itest là hệ ngoài, truy cập
READ-ONLY (xem app/integrations/itest/source.py).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import CurriculumTopic, ItestTopicMap, User
from app.db.session import get_session
from app.exam import service
from app.exam.assemble import (
    BoLuyen,
    MaTranReport,
    assemble_bo_luyen,
    kiem_tra_khop_ma_tran,
)
from app.exam.itest_suggest import (
    CellSuggestion,
    build_suggest_cells,
    suggest_for_cells,
)

router = APIRouter(prefix="/itest", tags=["itest"])


@router.get("/quiz")
async def quiz(
    topic: str | None = None,
    n: int = 0,  # 0 = lấy TẤT CẢ câu của đề
    user: User = Depends(get_current_user),
):
    """Lấy ĐỀ THẬT Toán lớp 6 (khớp chủ đề, đã publish) từ DB i-Test làm bài trắc
    nghiệm tương tác cho học sinh. Query i-Test trực tiếp (read-only), như repo
    dtp-chat-learning."""
    import asyncio

    from app.integrations.itest import quiz as quiz_mod

    if not settings.itest_database_url:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Chưa cấu hình kho đề i-Test trên server")
    try:
        return await asyncio.to_thread(
            quiz_mod.generate_quiz, topic, int(n) if int(n) > 0 else None
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except Exception:  # noqa: BLE001 - lỗi kết nối i-Test -> 503 thân thiện
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Hiện chưa lấy được bài trắc nghiệm, em thử lại sau nhé!")


class SuggestRequest(BaseModel):
    hoc_ky: str = Field(pattern="^(hk1|hk2)$")
    tong_so_cau: int = Field(ge=1, le=50)


class SuggestResponse(BaseModel):
    chi_tieu: dict[str, int]
    o: list[CellSuggestion]


class AssembleRequest(BaseModel):
    hoc_ky: str = Field(pattern="^(hk1|hk2)$")
    tong_so_cau: int = Field(ge=1, le=50)
    itest_picks: list[dict] = []
    ai_cau: list[dict] = []


class AssembleResponse(BaseModel):
    bo_luyen: BoLuyen
    ma_tran: MaTranReport


class MappingOut(BaseModel):
    id: int
    itest_tag: str
    topic_id: int | None
    muc_do: str | None
    status: str


def _require_teacher(user: User) -> None:
    if user.role != "giao_vien":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ giáo viên/quản trị được thao tác này")


@router.post("/suggest", response_model=SuggestResponse)
async def suggest(
    body: SuggestRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SuggestResponse:
    try:
        _bp, chi_tieu, _ti_le = await service.tinh_chi_tieu(
            session, hoc_ky=body.hoc_ky, tong_so_cau=body.tong_so_cau
        )
    except service.BlueprintNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    cells = await build_suggest_cells(session, _bp.id, chi_tieu)
    o = await suggest_for_cells(session, cells)
    return SuggestResponse(chi_tieu=chi_tieu, o=o)


@router.post("/assemble", response_model=AssembleResponse)
async def assemble(
    body: AssembleRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AssembleResponse:
    try:
        _bp, chi_tieu, _ti_le = await service.tinh_chi_tieu(
            session, hoc_ky=body.hoc_ky, tong_so_cau=body.tong_so_cau
        )
    except service.BlueprintNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    bo = assemble_bo_luyen(itest_picks=body.itest_picks, ai_cau=body.ai_cau)
    report = kiem_tra_khop_ma_tran(bo, chi_tieu)
    return AssembleResponse(bo_luyen=bo, ma_tran=report)


@router.get("/mappings", response_model=list[MappingOut])
async def list_mappings(
    status_filter: str = "cho_duyet",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MappingOut]:
    _require_teacher(user)
    rows = list(await session.scalars(
        select(ItestTopicMap).where(ItestTopicMap.status == status_filter)
    ))
    return [MappingOut(id=r.id, itest_tag=r.itest_tag, topic_id=r.topic_id,
                       muc_do=r.muc_do, status=r.status) for r in rows]


@router.post("/mappings/{map_id}/approve", response_model=MappingOut)
async def approve(
    map_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MappingOut:
    _require_teacher(user)
    from app.integrations.itest.mapping import approve_mapping

    try:
        row = await approve_mapping(session, map_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    await session.commit()
    return MappingOut(id=row.id, itest_tag=row.itest_tag, topic_id=row.topic_id,
                      muc_do=row.muc_do, status=row.status)


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(user: User = Depends(get_current_user)) -> dict:
    """Kích hoạt đồng bộ Itest (read-only) chạy nền. Chỉ giáo viên/quản trị."""
    _require_teacher(user)
    from app.ingestion.celery_app import sync_itest_task

    task = sync_itest_task.delay()
    return {"task_id": task.id, "message": "Đã xếp hàng đồng bộ Itest (chạy nền)."}

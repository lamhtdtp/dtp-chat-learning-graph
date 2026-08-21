"""CMS chuyên gia biên soạn giáo trình (mô hình mockup cms.html).

Chỉ GIÁO VIÊN / QUẢN TRỊ. Biên soạn nội dung 4 phần cho từng đơn vị kiến thức:
  ① Khái niệm  ② Minh họa (ảnh/video, video có thể upload thay bản AI)
  ③ Ví dụ      ④ Kiểm tra nhanh (KHÓA — sinh theo ma trận, xem app/lessons/quiz)
+ Hướng dẫn giảng dạy (GV) + trạng thái xuất bản (draft|review|published).

- GET  /cms/curriculum              — mục lục + trạng thái + độ hoàn thiện n/4
- GET  /cms/topics/{topic_id}       — nội dung đầy đủ (kèm đáp án) + yêu cầu cần đạt
- PUT  /cms/topics/{topic_id}       — lưu nội dung (upsert)
- POST /cms/topics/{topic_id}/ai-ingest       — AI soạn nháp khái niệm + ví dụ
- POST /cms/topics/{topic_id}/quiz/generate    — sinh lại kiểm tra nhanh theo ma trận
- POST /cms/topics/{topic_id}/nhac/generate    — sinh lời nhắc chủ động của trợ lý
- POST /cms/topics/{topic_id}/video            — upload/thay video minh họa
"""
import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import security
from app.api.deps import get_current_user
from app.config import settings
from app.exam import diem_khop
from app.db.models import (
    BlueprintCell, Book, CurriculumTopic, Grade, Subject, TopicContent, User,
)
from app.db.session import get_session
from app.lessons import bo_cuc as bo_cuc_svc
from app.lessons import ingest as ingest_svc
from app.lessons import media as media_svc
from app.lessons import nhac as nhac_svc
from app.lessons import quiz as quiz_svc
from app.llm.gateway import LLMUnavailable
from app.video import storage

log = logging.getLogger(__name__)

router = APIRouter(prefix="/cms", tags=["cms"])

_TRANG_THAI = {"draft", "review", "published"}
# Ai được biên soạn giáo trình. `chuyen_gia` là vai trò CMS-only (chỉ thấy phần
# Nội dung); `giao_vien` giữ lại vì họ cũng soạn/duyệt được.
_TAC_GIA = {"chuyen_gia", "giao_vien", "admin"}
_MAX_VIDEO_BYTES = 100 * 1024 * 1024  # 100MB — video minh họa ngắn
_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}


def _require_author(user: User) -> None:
    if user.role not in _TAC_GIA:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ giáo viên/quản trị được vào CMS")


def _check_nguon(nguon: str | None) -> None:
    """Chặn tư liệu nguồn quá dài — nó đi thẳng vào prompt soạn bài."""
    if nguon and len(nguon) > settings.cms_nguon_max_chars:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Tư liệu nguồn dài {len(nguon)} ký tự, tối đa {settings.cms_nguon_max_chars}.")


class CmsLimits(BaseModel):
    nguon_max_chars: int


@router.get("/limits", response_model=CmsLimits)
async def cms_limits(user: User = Depends(get_current_user)) -> CmsLimits:
    """Giới hạn ô nhập cho trình soạn biết TRƯỚC khi gửi (xem /tutor/limits)."""
    _require_author(user)
    return CmsLimits(nguon_max_chars=settings.cms_nguon_max_chars)


# Khoá được phép lưu trong 1 item minh hoạ. Chốt danh sách để trường chỉ-để-xem
# (url_xem — URL có chữ ký, hết hạn) KHÔNG bị client gửi ngược lên rồi ghi vào DB.
_MEDIA_KEYS = ("type", "url", "caption", "source", "concept_key")


def _media_for_view(items: list[dict]) -> list[dict]:
    """Thêm `url_xem` = URL đã ký cho media nội bộ, để trình soạn xem được ảnh/video.

    Giữ `url` THÔ: đó là giá trị lưu DB, ký vào đấy thì link hết hạn nằm luôn
    trong nội dung. Cặp url (lưu) / url_xem (hiển thị) tách hẳn nhau."""
    out = []
    for m in items:
        url = m.get("url") or ""
        out.append({**m, "url_xem": security.sign_media(url)} if url.startswith("/video/files/") else m)
    return out


def _media_for_save(items: list[dict]) -> list[dict]:
    """Lược item minh hoạ về đúng các khoá được lưu (bỏ url_xem và khoá lạ)."""
    return [{k: m[k] for k in _MEDIA_KEYS if k in m} for m in items]


def _completeness(c: TopicContent | None) -> dict:
    """Đủ 4 phần? (khái niệm, minh họa, ví dụ, kiểm tra nhanh)."""
    if c is None:
        return {"done": 0, "total": 4, "parts": {"khai_niem": False, "minh_hoa": False, "vi_du": False, "quiz": False}}
    parts = {
        "khai_niem": bool((c.khai_niem or "").strip()),
        "minh_hoa": len(json.loads(c.minh_hoa_json or "[]")) > 0,
        "vi_du": len(json.loads(c.vi_du_json or "[]")) > 0,
        "quiz": len(json.loads(c.quiz_json or "[]")) > 0,
    }
    return {"done": sum(parts.values()), "total": 4, "parts": parts}


async def _units(session: AsyncSession, mon: str, khoi: str, hoc_ky: str | None = None) -> list[dict]:
    """Mục lục khử trùng (giống lessons._units) — tái hiện ở đây để CMS độc lập.
    Lọc theo học kỳ nếu `hoc_ky` (hk1|hk2); None/"all" -> mọi học kỳ."""
    subject = await session.scalar(select(Subject).filter_by(name=mon))
    grade = await session.scalar(select(Grade).filter_by(name=khoi))
    if subject is None or grade is None:
        return []
    q = select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id)
    if hoc_ky in ("hk1", "hk2"):
        q = q.filter(CurriculumTopic.hoc_ky == hoc_ky)
    rows = list(await session.scalars(q.order_by(CurriculumTopic.order_index)))
    groups: list[dict] = []
    gidx: dict[str, dict] = {}
    seen_dv: dict[str, set] = {}
    for t in rows:
        mach = (t.mach_noi_dung or "").strip()
        dv = (t.don_vi_kien_thuc or "").strip()
        if not dv:
            continue
        g = gidx.get(mach.lower())
        if g is None:
            g = {"mach": mach, "dv": []}
            gidx[mach.lower()] = g
            seen_dv[mach.lower()] = set()
            groups.append(g)
        if dv.lower() not in seen_dv[mach.lower()]:
            seen_dv[mach.lower()].add(dv.lower())
            g["dv"].append({"topic_id": t.id, "ten": dv})
    return groups


# Danh mục lựa chọn cho CMS (đa lớp/môn/học kỳ — tương lai không chỉ Toán 6).
# Trả bộ chuẩn THCS + hợp với môn/khối đã có trong DB, để chuyên gia chọn.
_GRADES_CHUAN = ["Lớp 6", "Lớp 7", "Lớp 8", "Lớp 9"]
_SUBJECTS_CHUAN = ["Toán", "Ngữ văn", "Tiếng Anh", "Khoa học tự nhiên", "Lịch sử và Địa lí"]


@router.get("/catalog")
async def cms_catalog(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Lựa chọn Lớp / Môn / Học kỳ cho bộ lọc CMS. Gộp bộ chuẩn THCS với dữ liệu
    thật trong DB (để môn/khối mới thêm sau vẫn hiện)."""
    _require_author(user)
    db_grades = list(await session.scalars(select(Grade.name)))
    db_subjects = list(await session.scalars(select(Subject.name)))
    grades = list(dict.fromkeys(_GRADES_CHUAN + db_grades))
    subjects = list(dict.fromkeys(_SUBJECTS_CHUAN + db_subjects))
    return {
        "grades": grades,
        "subjects": subjects,
        "semesters": [{"value": "all", "label": "Cả năm"},
                      {"value": "hk1", "label": "Học kỳ 1"},
                      {"value": "hk2", "label": "Học kỳ 2"}],
    }


@router.get("/curriculum")
async def cms_curriculum(
    mon: str = "Toán", khoi: str = "Lớp 6", hoc_ky: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    _require_author(user)
    groups = await _units(session, mon, khoi, hoc_ky)
    contents = {c.topic_id: c for c in await session.scalars(select(TopicContent))}
    for g in groups:
        for d in g["dv"]:
            c = contents.get(d["topic_id"])
            d["trang_thai"] = c.trang_thai if c else "chua_bien_soan"
            d["completeness"] = _completeness(c)
            d["nguon"] = c.nguon if c else None
            d["ai"] = bool(c and c.ai_soan)  # cờ riêng, không dò chuỗi trong `nguon` nữa
    return groups


async def _yeu_cau_can_dat(session: AsyncSession, topic: CurriculumTopic) -> list[dict]:
    twins = list(await session.scalars(
        select(CurriculumTopic).filter_by(
            subject_id=topic.subject_id, grade_id=topic.grade_id,
            mach_noi_dung=topic.mach_noi_dung, don_vi_kien_thuc=topic.don_vi_kien_thuc,
        )
    ))
    ids = [t.id for t in twins] or [topic.id]
    cells = list(await session.scalars(select(BlueprintCell).where(BlueprintCell.topic_id.in_(ids))))
    seen, out = set(), []
    for c in cells:
        key = (c.yeu_cau_can_dat, c.muc_do)
        if c.yeu_cau_can_dat and key not in seen:
            seen.add(key)
            out.append({"yeu_cau": c.yeu_cau_can_dat, "muc_do": c.muc_do})
    return out


@router.get("/topics/{topic_id}")
async def cms_get_topic(
    topic_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_author(user)
    topic = await session.get(CurriculumTopic, topic_id)
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    c = await session.scalar(select(TopicContent).filter_by(topic_id=topic_id))
    base = {
        "topic_id": topic_id,
        "mach": (topic.mach_noi_dung or "").strip(),
        "dv": (topic.don_vi_kien_thuc or "").strip(),
        "yeu_cau_can_dat": await _yeu_cau_can_dat(session, topic),
    }
    if c is None:
        return {**base, "khai_niem": "", "minh_hoa": [], "vi_du": [], "quiz": [], "nhac": [],
                "khoi_dong": "", "hoat_dong": "", "luyen_tap": "", "bai_tap": "",
                "bo_cuc": bo_cuc_svc.doc(None),
                "day": None, "nguon": None, "trang_thai": "draft", "completeness": _completeness(None)}
    return {
        **base,
        "khai_niem": c.khai_niem,
        "khoi_dong": c.khoi_dong or "", "hoat_dong": c.hoat_dong or "",
        "luyen_tap": c.luyen_tap or "", "bai_tap": c.bai_tap or "",
        # Bố cục ĐẦY ĐỦ (kể cả phần ẩn) — CMS cần thấy cả phần đang ẩn để bật lại.
        "bo_cuc": bo_cuc_svc.doc(c.bo_cuc_json),
        # Video AI lưu lúc chưa render xong có url=None -> tra job DONE để hiện được.
        "minh_hoa": _media_for_view(
            await media_svc.fill_video_urls(session, json.loads(c.minh_hoa_json or "[]"))
        ),
        "vi_du": json.loads(c.vi_du_json or "[]"),
        "quiz": json.loads(c.quiz_json or "[]"),
        # Lời nhắc chủ động đã sinh sẵn — chuyên gia xem/sinh lại được như quiz.
        "nhac": nhac_svc.doc_nhac(c),
        "day": json.loads(c.day_json) if c.day_json else None,
        "nguon": c.nguon,
        "trang_thai": c.trang_thai,
        "completeness": _completeness(c),
    }


class TopicUpdate(BaseModel):
    khai_niem: str = ""
    khoi_dong: str = ""
    hoat_dong: str = ""
    luyen_tap: str = ""
    bai_tap: str = ""
    minh_hoa: list[dict] = []
    vi_du: list[dict] = []
    day: dict | None = None
    nguon: str | None = None
    trang_thai: str = "draft"
    # None = giữ nguyên cờ đang có (trình soạn không đụng tới); True/False = đặt
    # rõ (luồng "Nạp sách bằng AI" đặt True).
    ai_soan: bool | None = None


async def _get_or_create(session: AsyncSession, topic_id: int) -> TopicContent:
    c = await session.scalar(select(TopicContent).filter_by(topic_id=topic_id))
    if c is None:
        c = TopicContent(topic_id=topic_id)
        session.add(c)
    return c


@router.put("/topics/{topic_id}")
async def cms_save_topic(
    topic_id: int,
    body: TopicUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Lưu nội dung 4 phần + hướng dẫn dạy. KHÔNG đụng quiz (sinh theo ma trận)."""
    _require_author(user)
    if body.trang_thai not in _TRANG_THAI:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Trạng thái không hợp lệ")
    if await session.get(CurriculumTopic, topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    _check_nguon(body.nguon)
    c = await _get_or_create(session, topic_id)
    c.khai_niem = body.khai_niem
    c.khoi_dong, c.hoat_dong = body.khoi_dong, body.hoat_dong
    c.luyen_tap, c.bai_tap = body.luyen_tap, body.bai_tap
    c.minh_hoa_json = json.dumps(_media_for_save(body.minh_hoa), ensure_ascii=False)
    c.vi_du_json = json.dumps(body.vi_du, ensure_ascii=False)
    c.day_json = json.dumps(body.day, ensure_ascii=False) if body.day else None
    c.nguon = body.nguon
    if body.ai_soan is not None:
        c.ai_soan = body.ai_soan
    c.trang_thai = body.trang_thai
    out = {"topic_id": topic_id, "trang_thai": body.trang_thai, "completeness": _completeness(c)}
    await session.commit()
    return out


class IngestRequest(BaseModel):
    nguon: str = ""  # tư liệu chuyên gia dán vào (tuỳ chọn)
    media: bool = True  # sinh luôn ảnh + đặt hàng video ngắn


@router.post("/topics/{topic_id}/ai-ingest")
async def cms_ai_ingest(
    topic_id: int,
    body: IngestRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """AI soạn NHÁP khái niệm + ví dụ + minh hoạ, bám ngữ liệu SGK (Qdrant).

    KHÔNG lưu nội dung — chuyên gia rà soát rồi PUT. `media=True` thì sinh luôn
    ảnh (đồng bộ) và đặt hàng video ngắn (async qua Celery): request sẽ lâu hơn
    đáng kể vì mỗi ảnh là một lần gọi model sinh ảnh.
    """
    _require_author(user)
    topic = await session.get(CurriculumTopic, topic_id)
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    _check_nguon(body.nguon)   # chặn ở đây nữa: ai-ingest gửi nguon thẳng vào prompt
    try:
        draft = await ingest_svc.ingest_draft(session, topic_id, nguon=body.nguon)
    except LLMUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Hệ thống AI đang quá tải, thử lại sau nhé.")

    minh_hoa: list[dict] = []
    loi: list[str] = []
    # Nháp chữ rỗng = AI trả về thứ không bóc được. Trước đây im lặng, tác giả
    # tưởng bấm hụt; nói thẳng để họ bấm lại thay vì ngồi đoán.
    if not draft["khai_niem"] and not draft["vi_du"]:
        loi.append("AI trả về nội dung không đọc được — bấm “Gợi ý AI” lại lần nữa.")
    if body.media:
        anh, loi_anh = await media_svc.generate_images(topic_id, draft["anh"])
        minh_hoa += anh
        loi += loi_anh
        vid, loi_vid = await media_svc.request_video(
            session, topic, draft["video"], mon=draft["mon"] or "toan")
        if vid:
            minh_hoa.append(vid)
        loi += loi_vid
        # Không có media mà cũng không có lỗi = AI không đề xuất được gì. Phải nói
        # ra: im lặng thì tác giả ngồi nhìn khung trống, tưởng tính năng hỏng.
        if not minh_hoa and not loi:
            loi.append("AI chưa đề xuất được minh hoạ cho đơn vị này — bấm “Gợi ý AI” lại lần nữa.")
        await session.commit()   # VideoJob vừa tạo phải bền trước khi worker đọc

    return {
        "khai_niem": draft["khai_niem"],
        "vi_du": draft["vi_du"],
        "minh_hoa": _media_for_view(minh_hoa),
        "trang_sgk": draft["trang_sgk"],
        "thieu_sgk": draft["thieu_sgk"],
        "loi_media": loi,
    }


@router.post("/topics/{topic_id}/quiz/generate")
async def cms_generate_quiz(
    topic_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Sinh lại kiểm tra nhanh theo ma trận + cache. (Dùng chung service với /lessons.)"""
    _require_author(user)
    if await session.get(CurriculumTopic, topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    try:
        quiz = await quiz_svc.generate_quiz(session, topic_id)
    except LLMUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Hệ thống AI đang quá tải, thử lại sau nhé.")
    if not quiz:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI chưa soạn được câu hỏi hợp lệ, thử lại nhé.")
    c = await _get_or_create(session, topic_id)
    c.quiz_json = json.dumps(quiz, ensure_ascii=False)
    await session.commit()
    return {"topic_id": topic_id, "quiz": quiz, "so_cau": len(quiz)}


@router.post("/topics/{topic_id}/nhac/generate")
async def cms_generate_nhac(
    topic_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Sinh lời nhắc chủ động (hỏi lại sau khi HS đọc xong khái niệm) + cache.

    Sinh ở ĐÂY chứ không sinh online lúc học sinh đọc: mỗi lần cuộn qua khái niệm
    mà gọi LLM là một lượt, hạn mức ngày bay sạch trước khi em ấy kịp hỏi gì."""
    _require_author(user)
    if await session.get(CurriculumTopic, topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    try:
        nhac = await nhac_svc.generate_nhac(session, topic_id)
    except LLMUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Hệ thống AI đang quá tải, thử lại sau nhé.")
    if not nhac:
        # Tách hai nguyên nhân: thiếu đầu vào là việc của chuyên gia, còn AI trả
        # về hỏng là việc thử lại. Gộp một câu thì chuyên gia đi sửa nhầm chỗ.
        c0 = await session.scalar(select(TopicContent).filter_by(topic_id=topic_id))
        if not (c0 and (c0.khai_niem or "").strip()):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Cần soạn phần Khái niệm trước rồi mới sinh được lời nhắc.")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "AI chưa soạn được lời nhắc hợp lệ, thử lại nhé.")
    c = await _get_or_create(session, topic_id)
    c.nhac_json = json.dumps(nhac, ensure_ascii=False)
    await session.commit()
    return {"topic_id": topic_id, "nhac": nhac}


@router.post("/topics/{topic_id}/video")
async def cms_upload_video(
    topic_id: int,
    caption: str = "",
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upload video minh họa của chuyên gia (source='expert', ưu tiên hơn video
    AI). Thêm vào cuối danh sách minh họa. Trả minh_hoa đã cập nhật (URL thô;
    /lessons sẽ ký khi phục vụ HS)."""
    _require_author(user)
    if await session.get(CurriculumTopic, topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    if file.content_type not in _VIDEO_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Định dạng video không hỗ trợ (mp4/webm/mov)")
    data = await file.read()
    if len(data) > _MAX_VIDEO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Video quá lớn (tối đa 100MB)")

    ext = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}[file.content_type]
    name = f"expert_topic{topic_id}_{len(data)}{ext}"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        url = storage.save_video(tmp_path, name)
    finally:
        tmp_path.unlink(missing_ok=True)

    c = await _get_or_create(session, topic_id)
    minh_hoa = json.loads(c.minh_hoa_json or "[]")
    minh_hoa.append({"type": "video", "url": url, "caption": caption or "Video minh họa", "source": "expert"})
    c.minh_hoa_json = json.dumps(minh_hoa, ensure_ascii=False)
    out = {"topic_id": topic_id, "minh_hoa": _media_for_view(minh_hoa)}
    await session.commit()
    return out


@router.get("/tong-quan")
async def cms_tong_quan(
    mon: str = "Toán", khoi: str = "Lớp 6",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Số liệu trang Tổng quan của chuyên gia (REQ §2.1).

    Ba khối, mỗi khối trả lời một câu:
      - `kpi`        : quy mô + mức hoàn thiện (4 ô số lớn)
      - `theo_mach`  : mạch nào đang hụt (% = phần đã soạn / (số đơn vị × 7))
      - `viec_can_lam`: việc cụ thể phải làm tiếp, kèm số lượng
    """
    _require_author(user)
    subject = await session.scalar(select(Subject).filter_by(name=mon))
    grade = await session.scalar(select(Grade).filter_by(name=khoi))
    if subject is None or grade is None:
        return {"kpi": {}, "theo_mach": [], "viec_can_lam": []}

    topics = list(await session.scalars(
        select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id)
        .order_by(CurriculumTopic.order_index)))
    ids = [t.id for t in topics]
    contents = {c.topic_id: c for c in await session.scalars(
        select(TopicContent).where(TopicContent.topic_id.in_(ids or [0])))}

    TONG_PHAN = len(bo_cuc_svc.PHAN)
    thieu_kt = quiz_rong = du_7 = dang_soan = 0
    mach: dict[str, dict] = {}
    for t in topics:
        c = contents.get(t.id)
        n = bo_cuc_svc.da_soan(c) if c else 0
        if n >= TONG_PHAN:
            du_7 += 1
        elif n > 0:
            dang_soan += 1
        if not c or not (c.khai_niem or "").strip():
            thieu_kt += 1
        if not c or json.loads(c.quiz_json or "[]") == []:
            quiz_rong += 1
        m = mach.setdefault((t.mach_noi_dung or "").strip(), {"mach": (t.mach_noi_dung or "").strip(),
                                                              "so_dv": 0, "da": 0})
        m["so_dv"] += 1
        m["da"] += n

    ycd = await session.scalar(select(func.count()).select_from(BlueprintCell)
                               .where(BlueprintCell.topic_id.in_(ids or [0]))) or 0

    theo_mach = [{**m, "phan_tram": round(100 * m["da"] / (m["so_dv"] * TONG_PHAN))
                  if m["so_dv"] else 0} for m in mach.values()]

    viec = [
        {"so": thieu_kt, "mo": "đơn vị chưa có Kiến thức trọng tâm", "di": "content"},
        {"so": quiz_rong, "mo": "đơn vị chưa sinh Kiểm tra nhanh", "di": "content"},
        {"so": dang_soan, "mo": "đơn vị đang soạn dở", "di": "content"},
        {"so": 0, "mo": "dòng ma trận cần gán tay (điểm khớp < 0.8)", "di": "matrix"},
    ]
    return {
        "kpi": {"tong_dv": len(topics), "du_7_phan": du_7, "ycd": ycd, "dang_soan": dang_soan,
                "tong_phan": TONG_PHAN},
        "theo_mach": theo_mach,
        "viec_can_lam": [v for v in viec if v["so"] > 0],
    }


class BoCucBody(BaseModel):
    bo_cuc: list[dict] = []   # [{"id": "...", "an": bool}] — id lạ bị lược ở service


@router.put("/topics/{topic_id}/bo-cuc")
async def cms_luu_bo_cuc(
    topic_id: int, body: BoCucBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Lưu thứ tự + ẩn/hiện 7 phần (REQ §2.2).

    Tách khỏi PUT /topics/{id} vì hai thao tác khác nhịp: đổi thứ tự là một cú bấm
    `↑`/`↓` cần lưu ngay, còn soạn nội dung thì bấm 💾 mới lưu. Gộp lại thì mỗi lần
    kéo thứ tự sẽ ghi đè cả nội dung đang sửa dở.
    """
    _require_author(user)
    if await session.get(CurriculumTopic, topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    c = await _get_or_create(session, topic_id)
    c.bo_cuc_json = bo_cuc_svc.ghi(body.bo_cuc)
    out = {"topic_id": topic_id, "bo_cuc": bo_cuc_svc.doc(c.bo_cuc_json)}
    await session.commit()
    return out


@router.post("/topics/{topic_id}/phan/{phan}/ai")
async def cms_ai_theo_phan(
    topic_id: int, phan: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """AI soạn gợi ý cho ĐÚNG MỘT phần, bám yêu cầu cần đạt của đơn vị (REQ §2.2).

    KHÔNG sinh cả bài: chuyên gia bấm "✨ AI hỗ trợ" ở hàng nào thì chỉ muốn phần
    đó. Sinh cả bài sẽ đè lên các phần họ đã soạn tay.

    Không tự lưu — trả nháp để chuyên gia rà rồi PUT như luồng ai-ingest.
    """
    _require_author(user)
    if phan not in bo_cuc_svc.IDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Phần không hợp lệ. Hợp lệ: {', '.join(bo_cuc_svc.IDS)}")
    if phan in ("minh_hoa", "vi_du"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Minh hoạ và Ví dụ sinh bằng “Gợi ý AI” ở trình soạn, không qua đường này.")
    if await session.get(CurriculumTopic, topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn vị kiến thức")
    try:
        html = await ingest_svc.soan_phan(session, topic_id, phan)
    except LLMUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Hệ thống AI đang quá tải, thử lại sau nhé.")
    if not html:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI chưa soạn được nội dung, thử lại nhé.")
    return {"topic_id": topic_id, "phan": phan, "html": html}


# Học kỳ 1 gồm 4 mạch này (khớp HK1_MACH ở web/src/learn/LearnApp.tsx). Backend
# chỉ có `CurriculumTopic.hoc_ky` khi ma trận nạp kèm học kỳ; thiếu thì suy từ tên
# mạch để cây danh mục vẫn có nhóm HỌC KỲ.
_HK1_MACH = {
    "số tự nhiên", "số nguyên",
    "các hình phẳng trong thực tiễn", "tính đối xứng của hình phẳng",
}


def _hoc_ky(t: CurriculumTopic) -> str:
    if t.hoc_ky in ("hk1", "hk2"):
        return t.hoc_ky
    return "hk1" if (t.mach_noi_dung or "").strip().lower() in _HK1_MACH else "hk2"


@router.get("/danh-muc")
async def cms_danh_muc(
    mon: str = "Toán", khoi: str = "Lớp 6",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Cây danh mục: HỌC KỲ → mạch → đơn vị, kèm node ôn tập (REQ §2.3).

    Node ôn tập KHÔNG phải `CurriculumTopic` mới — chúng là *view* sinh từ mạch /
    học kỳ, đề lấy từ `blueprint_cells` của toàn bộ đơn vị trong phạm vi. Tạo bản
    ghi thật cho chúng sẽ làm mục lục và tiến độ đếm sai.
    """
    _require_author(user)
    subject = await session.scalar(select(Subject).filter_by(name=mon))
    grade = await session.scalar(select(Grade).filter_by(name=khoi))
    if subject is None or grade is None:
        return {"hoc_ky": []}

    topics = list(await session.scalars(
        select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id)
        .order_by(CurriculumTopic.order_index)))
    ids = [t.id for t in topics]
    contents = {c.topic_id: c for c in await session.scalars(
        select(TopicContent).where(TopicContent.topic_id.in_(ids or [0])))}
    ycd_rows = (await session.execute(
        select(BlueprintCell.topic_id, func.count())
        .where(BlueprintCell.topic_id.in_(ids or [0]))
        .group_by(BlueprintCell.topic_id))).all()
    ycd = {tid: n for tid, n in ycd_rows}

    TONG = len(bo_cuc_svc.PHAN)
    hk: dict[str, dict] = {}
    for t in topics:
        k = _hoc_ky(t)
        nhom = hk.setdefault(k, {"hoc_ky": k, "mach": {}})
        ten_mach = (t.mach_noi_dung or "").strip()
        m = nhom["mach"].setdefault(ten_mach, {"mach": ten_mach, "dv": []})
        ten = (t.don_vi_kien_thuc or "").strip()
        if not ten or any(d["ten"].lower() == ten.lower() for d in m["dv"]):
            continue    # mục lục khử trùng theo tên: không khử thì cây hiện lặp
        c = contents.get(t.id)
        n = bo_cuc_svc.da_soan(c) if c else 0
        m["dv"].append({
            "topic_id": t.id, "ten": ten, "da_soan": n, "tong_phan": TONG,
            "ycd": ycd.get(t.id, 0),
            # 3 mức: Đủ (7/7) · Đang soạn (1-6) · Chưa soạn (0)
            "tinh_trang": "du" if n >= TONG else ("dang" if n else "chua"),
            "trang_thai": c.trang_thai if c else "chua_bien_soan",
        })

    return {"hoc_ky": [
        {"hoc_ky": k,
         "mach": [{**m, "so_dv": len(m["dv"]),
                   # Node "🔁 Ôn tập chương" ở CUỐI mỗi mạch, cùng cấp đơn vị
                   "on_tap": {"pham_vi": "mach", "gia_tri": m["mach"], "so_cau": 12}}
                  for m in v["mach"].values()],
         # Node "🏁 Ôn tập cuối học kỳ" ở CUỐI học kỳ, KHÔNG thụt
         "on_tap_ky": {"pham_vi": "hoc_ky", "gia_tri": k, "so_cau": 30}}
        for k, v in sorted(hk.items())
    ]}


@router.get("/kho-sgk")
async def cms_kho_sgk(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Số liệu kho tri thức + danh sách sách đã nạp (REQ §2.4).

    Đếm THẬT trong Qdrant, không đọc từ bảng đếm sẵn: nạp lại sách hay xoá
    collection thì bảng đếm sẽ nói dối trong khi kho đã khác.

    Qdrant hỏng -> trả `kho_loi=True` và số 0, KHÔNG 500: trang này còn phần danh
    sách sách (từ Postgres) vẫn dùng được.
    """
    _require_author(user)
    books = list(await session.scalars(select(Book).order_by(Book.id)))
    subs = {s.id: s.name for s in await session.scalars(select(Subject))}
    grades = {g.id: g.name for g in await session.scalars(select(Grade))}

    tong_doan = trang = co_nguon = 0
    kho_loi = False
    try:
        from qdrant_client import AsyncQdrantClient

        cl = AsyncQdrantClient(url=settings.qdrant_url)
        tong_doan = (await cl.count(settings.qdrant_collection, exact=True)).count
        # Số TRANG và % có dẫn nguồn phải quét payload; giới hạn mẫu để trang admin
        # không treo trên kho lớn.
        pages: set = set()
        điểm, _ = await cl.scroll(settings.qdrant_collection, limit=5000, with_payload=True)
        for p in điểm:
            pl = p.payload or {}
            if pl.get("page_no") is not None:
                pages.add((pl.get("sach"), pl.get("tap"), pl.get("page_no")))
            if pl.get("nguon"):
                co_nguon += 1
        trang = len(pages)
        mau = len(điểm) or 1
        co_nguon = round(100 * co_nguon / mau)
    except Exception as e:   # noqa: BLE001 — kho lỗi không được chặn cả trang
        kho_loi = True
        log.warning("Không đọc được kho SGK cho trang Nạp sách: %s", e)

    return {
        "kpi": {"so_sach": len(books), "so_trang": trang,
                "so_doan": tong_doan, "pt_dan_nguon": co_nguon},
        "kho_loi": kho_loi,
        "sach": [{"id": b.id, "ten": b.name, "mon": subs.get(b.subject_id, "?"),
                  "khoi": grades.get(b.grade_id, "?"), "tap": b.semester,
                  "source_ref": b.source_ref} for b in books],
    }


@router.get("/ma-tran")
async def cms_ma_tran(
    mon: str = "Toán", khoi: str = "Lớp 6",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Đối chiếu ma trận đặc tả với danh mục chương trình (REQ §2.5).

    CHỈ ĐỌC — không gán, không tạo đơn vị mới. Ba khối:
      - `tong`     : khớp chắc chắn (≥0.8) · cần xem lại (0.5–0.8) · chưa gán (<0.5)
      - `ti_le`    : % theo mức độ, mỗi nhóm ô gộp cộng MỘT lần
      - `anh_xa`   : bảng Mức độ | Yêu cầu cần đạt | Đơn vị | Độ khớp

    Điểm khớp tính LẠI giữa tên đơn vị của cell và danh mục hiện tại, nên nếu ai
    sửa tên đơn vị trong danh mục sau khi nạp ma trận, bảng này sẽ chỉ ra ngay.
    """
    _require_author(user)
    subject = await session.scalar(select(Subject).filter_by(name=mon))
    grade = await session.scalar(select(Grade).filter_by(name=khoi))
    if subject is None or grade is None:
        return {"tong": {}, "ti_le": {}, "anh_xa": [], "so_dong": 0}

    topics = list(await session.scalars(
        select(CurriculumTopic).filter_by(subject_id=subject.id, grade_id=grade.id)))
    theo_id = {t.id: t for t in topics}
    cells = list(await session.scalars(
        select(BlueprintCell).where(BlueprintCell.topic_id.in_(list(theo_id) or [0]))
        .order_by(BlueprintCell.id)))

    anh_xa, dem = [], {"cao": 0, "vua": 0, "thap": 0, "chua_do": 0}
    for c in cells:
        t = theo_id.get(c.topic_id)
        # Điểm ĐÃ LƯU lúc nạp. Không tính lại: tên gốc trong .docx không còn nên
        # so tên đã gán với chính nó sẽ luôn ra 100% và bảng thành vô nghĩa.
        d = c.diem_khop
        if d is None:
            dem["chua_do"] += 1
            loai = None
        else:
            loai = diem_khop.xep_loai(d)
            dem[loai] += 1
        anh_xa.append({
            "muc_do": c.muc_do, "ycd": c.yeu_cau_can_dat,
            "don_vi": (t.don_vi_kien_thuc or "").strip() if t else "(chưa gán)",
            "mach": (t.mach_noi_dung or "").strip() if t else "",
            # Tên trong .docx khác tên danh mục -> hiện cả hai để người duyệt thấy
            # vì sao điểm thấp.
            "ten_nguon": c.ten_nguon,
            "lech_ten": bool(c.ten_nguon and t and
                             diem_khop.chuan(c.ten_nguon) != diem_khop.chuan(t.don_vi_kien_thuc or "")),
            "diem": None if d is None else round(d * 100), "loai": loai,
        })

    # Đơn vị do lần nạp ma trận TỰ TẠO — tên lấy thô từ .docx nên phải rà lại.
    # Giữ hành vi tự tạo (quyết định (b)) nhưng không để nó xảy ra âm thầm.
    tu_mt = [{"topic_id": t.id, "ten": (t.don_vi_kien_thuc or "").strip(),
              "mach": (t.mach_noi_dung or "").strip()}
             for t in topics if getattr(t, "tu_ma_tran", False)]

    return {
        "tong": {"khop": dem["cao"], "xem_lai": dem["vua"], "chua_gan": dem["thap"],
                 "chua_do": dem["chua_do"]},
        "tu_ma_tran": tu_mt,
        "ti_le": diem_khop.tong_ti_le_theo_muc_do(cells),
        "anh_xa": anh_xa[:200],
        "so_dong": len(cells),
    }

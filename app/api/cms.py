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
- POST /cms/topics/{topic_id}/video            — upload/thay video minh họa
"""
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import security
from app.api.deps import get_current_user
from app.config import settings
from app.db.models import BlueprintCell, CurriculumTopic, Grade, Subject, TopicContent, User
from app.db.session import get_session
from app.lessons import ingest as ingest_svc
from app.lessons import media as media_svc
from app.lessons import quiz as quiz_svc
from app.llm.gateway import LLMUnavailable
from app.video import storage

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
        return {**base, "khai_niem": "", "minh_hoa": [], "vi_du": [], "quiz": [],
                "day": None, "nguon": None, "trang_thai": "draft", "completeness": _completeness(None)}
    return {
        **base,
        "khai_niem": c.khai_niem,
        # Video AI lưu lúc chưa render xong có url=None -> tra job DONE để hiện được.
        "minh_hoa": _media_for_view(
            await media_svc.fill_video_urls(session, json.loads(c.minh_hoa_json or "[]"))
        ),
        "vi_du": json.loads(c.vi_du_json or "[]"),
        "quiz": json.loads(c.quiz_json or "[]"),
        "day": json.loads(c.day_json) if c.day_json else None,
        "nguon": c.nguon,
        "trang_thai": c.trang_thai,
        "completeness": _completeness(c),
    }


class TopicUpdate(BaseModel):
    khai_niem: str = ""
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

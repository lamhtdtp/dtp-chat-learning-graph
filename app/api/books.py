"""Serve ảnh trang SGK gốc (để UI mở modal "xem trang sách" khi bấm citation).

Ảnh nằm trên đĩa: data/books/maths/6/{tap}/{page}.png (Toán lớp 6).

Bảo vệ: thẻ <img> không gửi được header Authorization, nên dùng URL KÝ (HMAC có
hạn). Client (đã đăng nhập) gọi GET /books/pages-url/{tap}/{page} bằng Bearer để
lấy link ký, rồi gán vào <img>. GET /books/pages/... chỉ phục vụ khi chữ ký hợp
lệ + chưa hết hạn -> không tải được bằng URL đoán mò. Vẫn chặn path traversal.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import security
from app.api.deps import get_current_user
from app.config import settings
from app.db.models import CurriculumTopic, Grade, Subject, User
from app.db.session import get_session
from app.llm import cache, gateway
from app.video.concept import detect_concept

router = APIRouter(prefix="/books", tags=["books"])

# Tên môn (Subject.name) -> giá trị mon dùng nhận diện khái niệm video (concept.py).
_MON_CONCEPT = {"Toán": "toan", "Tiếng Anh": "tieng_anh"}

# Ảnh trang theo MÔN — không hard-code Toán nữa (citation môn Anh phải mở đúng
# sách Anh). `mon` nhận cả key frontend ("toan"/"anh") lẫn giá trị Qdrant
# ("tieng_anh"...); ánh xạ trùng với app/ingestion/tasks.py::_SUBJECT_FOLDER.
_BOOK_BASE = Path("data/books").resolve()
_KHOI_DIR = "6"
_MON_FOLDER = {
    "toan": "maths", "maths": "maths",
    "anh": "english", "tieng_anh": "english", "english": "english",
}


def _book_root(mon: str) -> Path:
    return (_BOOK_BASE / _MON_FOLDER.get(mon, "maths") / _KHOI_DIR).resolve()


# Markdown OCR mỗi trang (đã sinh sẵn lúc ingest) — nguồn để tóm tắt trang.
# Bố cục khớp app/ingestion/tasks.py: data_processed/<folder>/tap{tap}/{page}.md
_PROCESSED_BASE = Path("data_processed").resolve()
_SUMMARY_MAX_CHARS = 6000  # chặn token: trang dài chỉ lấy phần đầu
_SUMMARY_TTL = 30 * 24 * 3600
_SUMMARY_PROMPT = (
    "Tóm tắt trang sách giáo khoa sau thành 2–4 câu tiếng Việt ngắn gọn, dễ hiểu "
    "cho học sinh lớp 6. Chỉ nêu Ý CHÍNH (khái niệm/quy tắc/ví dụ tiêu biểu), KHÔNG "
    "liệt kê bài tập, không thêm thông tin ngoài trang. Nội dung trang:\n\n"
)


def _md_path(mon: str, tap: int, page: int) -> Path | None:
    folder = _MON_FOLDER.get(mon, "maths")
    p = (_PROCESSED_BASE / folder / f"tap{tap}" / f"{page}.md").resolve()
    return p if _PROCESSED_BASE in p.parents and p.is_file() else None


def _page_path(mon: str, tap: int, page: int) -> Path | None:
    """Đường dẫn ảnh trang, hỗ trợ 2 bố cục như ingestion: có thư mục tập
    (maths/6/<tap>/<page>.png) hoặc phẳng (english/6/<page>.png). Chặn path
    traversal: file phải nằm trong thư mục môn."""
    root = _book_root(mon)
    for cand in (root / str(tap) / f"{page}.png", root / f"{page}.png"):
        p = cand.resolve()
        if root in p.parents and p.is_file():
            return p
    return None


@router.get("/topics")
async def get_topics(
    mon: str = "Toán",
    khoi: str = "Lớp 6",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Danh mục chương trình cho panel chủ đề trong chat — lấy từ taxonomy thật
    `curriculum_topics` (không hard-code frontend). Gom theo mạch nội dung, giữ
    thứ tự order_index, khử trùng đơn vị kiến thức.

    Mỗi đơn vị kiến thức có cờ `co_video` = có khớp KHÁI NIỆM video cố định không
    (concept.py) -> chat sẽ đính được video cho chủ đề đó. Item/nhóm có video được
    đẩy LÊN ĐẦU (giữ nguyên thứ tự tương đối còn lại) để học sinh thấy trước."""
    subject = await session.scalar(select(Subject).filter_by(name=mon))
    grade = await session.scalar(select(Grade).filter_by(name=khoi))
    if subject is None or grade is None:
        return []
    rows = list(await session.scalars(
        select(CurriculumTopic)
        .filter_by(subject_id=subject.id, grade_id=grade.id)
        .order_by(CurriculumTopic.order_index)
    ))
    import re

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip())

    mon_cc = _MON_CONCEPT.get(mon, "toan")
    groups: list[dict] = []
    index: dict[str, dict] = {}
    for t in rows:
        mach = norm(t.mach_noi_dung)
        dv = norm(t.don_vi_kien_thuc)
        g = index.get(mach.lower())
        if g is None:
            g = {"mach_noi_dung": mach, "items": [], "_seen": set()}
            index[mach.lower()] = g
            groups.append(g)
        if dv and dv.lower() not in g["_seen"]:
            g["_seen"].add(dv.lower())
            g["items"].append({"ten": dv, "co_video": detect_concept(dv, mon_cc) is not None})
    for g in groups:
        g.pop("_seen", None)
        # item có video lên đầu (stable: giữ thứ tự order_index trong mỗi nhóm)
        g["items"].sort(key=lambda it: not it["co_video"])
        g["co_video"] = any(it["co_video"] for it in g["items"])
    # nhóm có video lên đầu (stable)
    groups.sort(key=lambda gr: not gr["co_video"])
    return groups


@router.get("/pages-url/{mon}/{tap}/{page}")
async def get_page_url(
    mon: str, tap: int, page: int, user: User = Depends(get_current_user)
) -> dict:
    """Cấp URL ký (có hạn) cho 1 trang SGK theo MÔN — chỉ user đã đăng nhập.
    `mon` nằm trong chữ ký nên không thể đổi môn sau khi ký."""
    if mon not in _MON_FOLDER or tap not in (1, 2) or page < 1:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trang không hợp lệ")
    return {"url": security.sign_media(f"/books/pages/{mon}/{tap}/{page}")}


@router.get("/pages/{mon}/{tap}/{page}")
async def get_page_image(
    mon: str, tap: int, page: int, exp: str | None = None, sig: str | None = None
) -> FileResponse:
    if not security.verify_media(f"/books/pages/{mon}/{tap}/{page}", exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Link ảnh không hợp lệ hoặc đã hết hạn")
    if mon not in _MON_FOLDER or tap not in (1, 2) or page < 1:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trang không hợp lệ")
    path = _page_path(mon, tap, page)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy trang")
    return FileResponse(path, media_type="image/png")


@router.get("/summary/{mon}/{tap}/{page}")
async def get_page_summary(
    mon: str, tap: int, page: int, user: User = Depends(get_current_user)
) -> dict:
    """Tóm tắt nội dung 1 trang SGK cho modal xem trang (lazy + cache Redis).
    Nguồn = markdown OCR sẵn có của trang; sinh tóm tắt tầng rẻ khi mở lần đầu,
    cache theo (sgk_version, môn, tập, trang). Trang chưa OCR -> summary=None.
    Tóm tắt là PHỤ: lỗi sinh tóm tắt không được làm hỏng việc xem ảnh trang."""
    if mon not in _MON_FOLDER or tap not in (1, 2) or page < 1:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trang không hợp lệ")

    key = f"booksum:{settings.sgk_version}:{_MON_FOLDER[mon]}:{tap}:{page}"
    cached = await cache.get(key)
    if cached is not None:
        return {"summary": cached}

    md_path = _md_path(mon, tap, page)
    if md_path is None:
        return {"summary": None}  # trang chưa có OCR -> không tóm tắt được
    try:
        content = md_path.read_text(encoding="utf-8").strip()[:_SUMMARY_MAX_CHARS]
        if not content:
            return {"summary": None}
        summary = (await gateway.complete(
            task="summarize_page",
            messages=[{"role": "user", "content": _SUMMARY_PROMPT + content}],
        )).strip()
    except Exception:  # noqa: BLE001 - tóm tắt là phụ, không làm hỏng modal
        return {"summary": None}

    await cache.set(key, summary, ttl=_SUMMARY_TTL)
    return {"summary": summary}

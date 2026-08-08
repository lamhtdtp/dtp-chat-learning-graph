"""AI nạp nháp nội dung bài học cho CMS (chuyên gia rà soát trước khi duyệt).

Sinh phần ① Khái niệm (HTML thuần) + ③ ví dụ có lời giải + ĐỀ XUẤT minh hoạ ②
(ảnh + 1 video ngắn), GROUNDING trên NGỮ LIỆU SGK lấy từ Qdrant — cùng kho, cùng
retriever với trợ lý hỏi–đáp của HS (app/graph/nodes/qa.py), nên nội dung biên
soạn và nội dung trả lời HS bám cùng một quyển sách.

`nguon` (chuyên gia dán tay) KHÔNG bị bỏ: nó được ưu tiên hơn ngữ cảnh retrieve
vì là trích đoạn người thật chọn cho đúng đơn vị này.

Không đủ ngữ liệu SGK -> VẪN soạn theo chuẩn chương trình nhưng trả cờ
`thieu_sgk=True` để CMS cảnh báo "nháp này không bám SGK, rà kỹ". Cố ý khác
pipeline video (raise PipelineError): ở đây kết quả là NHÁP có người duyệt, thà
đưa được cái để sửa hơn là chặn chuyên gia lại.

KHÔNG tự lưu nội dung — trả nháp để chuyên gia chỉnh rồi PUT. Riêng ẢNH sinh ra
buộc phải ghi vào storage mới có URL để xem, nên file ảnh tồn tại ngay cả khi
chuyên gia bỏ nháp (rác chấp nhận được, đổi lấy việc xem được ảnh trước khi lưu).
"""
import json
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BlueprintCell, CurriculumTopic, Grade, Subject
from app.graph.grounding import has_grounding
from app.llm import gateway, jsonfix
from app.llm.gateway import LLMUnavailable
from app.retrieval import retriever
from app.retrieval.retriever import RetrievedChunk

# Số đoạn SGK nạp vào prompt + ngưỡng điểm — giữ khớp tutor.ask/pipeline video để
# nội dung biên soạn không "thấy" nhiều/ít ngữ liệu hơn phần trả lời HS.
_TOP_K = 6
_SCORE_THRESHOLD = 0.4
_MAX_ANH = 2   # số ảnh tối đa xin AI đề xuất (mỗi ảnh là 1 lần gọi API sinh ảnh)


def _slug(name: str) -> str:
    """Tên hiển thị trong Postgres -> giá trị payload trong Qdrant.

    "Toán" -> "toan", "Tiếng Anh" -> "tieng_anh", "Lớp 6" -> "lop_6". Bỏ dấu
    bằng NFD rồi lược dấu tổ hợp, thay khoảng trắng bằng "_". Dùng chung cho cả
    môn và khối vì cùng quy tắc — không cần bảng tra tay như tutor._MON_QDRANT.
    """
    no_mark = "".join(c for c in unicodedata.normalize("NFD", name.strip())
                      if not unicodedata.combining(c))
    return "_".join(no_mark.lower().split())


async def _mon_khoi(session: AsyncSession, topic: CurriculumTopic) -> tuple[str | None, str | None]:
    """(mon, khoi) dạng Qdrant cho topic. None nếu thiếu bản ghi môn/khối."""
    subject = await session.get(Subject, topic.subject_id)
    grade = await session.get(Grade, topic.grade_id)
    return (_slug(subject.name) if subject else None, _slug(grade.name) if grade else None)


def _sgk_context(chunks: list[RetrievedChunk]) -> str:
    """Ngữ cảnh gắn nhãn [tr.N] — cùng định dạng qa_node dùng, để prompt yêu cầu
    trích số trang là làm được thật."""
    return "\n\n".join(f"[tr.{c.page_no}] {c.content}" for c in chunks)


def _prompt(dv: str, mach: str, mon_ten: str, khoi_ten: str,
            ycd: list[str], nguon: str, sgk: str) -> str:
    ycd_text = "\n".join(f"- {y}" for y in ycd) if ycd else "(theo chuẩn chương trình)"
    if sgk:
        nguon_block = (
            "NGỮ LIỆU SGK (bám sát — đây là sách trường đang dùng):\n"
            f"{sgk}\n\n"
            "QUY TẮC BÁM SÁCH:\n"
            "- Chỉ dùng định nghĩa, ký hiệu, thuật ngữ và cách trình bày CÓ trong ngữ liệu trên.\n"
            "- Không đưa kiến thức ngoài ngữ liệu. Thiếu ý nào thì soạn ngắn hơn, không bù bằng kiến thức ngoài sách.\n"
            "- Mỗi ý lấy từ đoạn nào thì chèn [tr.N] tương ứng vào cuối ý đó, dùng đúng số trang có trong ngữ liệu.\n"
        )
    else:
        nguon_block = (
            "NGỮ LIỆU SGK: (không tìm được đoạn nào khớp trong kho SGK)\n"
            "-> Soạn theo chuẩn Chương trình GDPT 2018. KHÔNG bịa số trang [tr.N].\n"
        )
    nguon_tay = (
        f"\nTƯ LIỆU CHUYÊN GIA DÁN VÀO (ưu tiên CAO NHẤT, cao hơn ngữ liệu trên):\n{nguon}\n"
        if nguon.strip() else ""
    )
    return (
        f'Soạn nội dung dạy học cho đơn vị kiến thức "{dv}" (mạch "{mach}"), môn {mon_ten} '
        f"{khoi_ten}, ngắn gọn, dễ hiểu với học sinh {khoi_ten.lower()}.\n\n"
        f"YÊU CẦU CẦN ĐẠT:\n{ycd_text}\n\n"
        f"{nguon_block}{nguon_tay}\n"
        "Trả JSON THUẦN:\n"
        '{"khai_niem": "<HTML: vài thẻ <p>, có thể <b>/<blockquote>, KHÔNG tiêu đề>", '
        '"vi_du": [{"de": "đề bài", "giai": "lời giải từng bước (HTML ngắn)"}]}\n'
        "Soạn 2–3 ví dụ từ dễ đến vận dụng."
    )


def _prompt_media(dv: str, mach: str, noi_dung: str) -> str:
    """Prompt RIÊNG cho đề xuất minh hoạ.

    Cố ý tách khỏi prompt soạn bài: gộp chung thì model dồn sức vào phần nội dung
    bám SGK rồi BỎ RƠI hai trường phụ — đã quan sát thật, cùng một prompt lúc trả
    lúc không, và nhánh parse lặng lẽ bỏ qua nên người dùng thấy trống mà không
    có lỗi nào. Prompt ngắn, chỉ một việc -> ổn định hơn hẳn, và chạy ở tầng rẻ.
    """
    return (
        f'Đề xuất minh hoạ cho bài học "{dv}" (mạch "{mach}").\n\n'
        f"NỘI DUNG BÀI HỌC (minh hoạ phải đúng nội dung này):\n{noi_dung}\n\n"
        f"Cần: {_MAX_ANH} ảnh tĩnh + 1 video ngắn.\n"
        "- `prompt` của ảnh là câu lệnh TIẾNG ANH cho model sinh ảnh: hình minh hoạ "
        "giáo dục, nền phẳng, phong cách sách giáo khoa, và PHẢI ghi rõ không có "
        "chữ/số trong ảnh (model sinh ảnh viết chữ tiếng Việt hay sai — chữ sai còn "
        "tệ hơn không có chữ).\n"
        "- `chu_de` của video là một chủ đề ngắn nằm trong phạm vi bài này, để hệ "
        "thống dựng video giảng bài.\n"
        "- `caption` viết bằng tiếng Việt, ngắn gọn.\n\n"
        "Trả JSON THUẦN, KHÔNG kèm giải thích:\n"
        '{"anh": [{"caption": "…", "prompt": "…, no text, no letters, no numbers"}], '
        '"video": {"chu_de": "…", "caption": "…"}}'
    )


async def goi_y_media(dv: str, mach: str, noi_dung: str) -> dict:
    """{anh, video} — đề xuất minh hoạ cho nội dung vừa soạn. Lỗi -> rỗng."""
    if not noi_dung.strip():
        return {"anh": [], "video": None}
    raw = await gateway.complete(
        task="media_suggest",
        messages=[{"role": "user", "content": _prompt_media(dv, mach, noi_dung)}],
        max_tokens=1024,
    )
    d = _parse(raw)
    return {"anh": d["anh"], "video": d["video"]}


def _parse(raw: str) -> dict:
    """Bóc nháp; phần nào hỏng thì bỏ phần đó, không làm sập cả nháp."""
    empty = {"khai_niem": "", "vi_du": [], "anh": [], "video": None}
    data = jsonfix.boc_json(raw)   # chịu được escape LaTeX sai — xem app/llm/jsonfix
    if not isinstance(data, dict):
        return empty

    vi_du = []
    for e in data.get("vi_du", []) if isinstance(data.get("vi_du"), list) else []:
        if isinstance(e, dict) and str(e.get("de", "")).strip():
            vi_du.append({"de": str(e["de"]).strip(), "giai": str(e.get("giai", "")).strip()})

    anh = []
    for a in data.get("anh", []) if isinstance(data.get("anh"), list) else []:
        if isinstance(a, dict) and str(a.get("prompt", "")).strip():
            anh.append({"prompt": str(a["prompt"]).strip(),
                        "caption": str(a.get("caption", "")).strip() or "Hình minh hoạ"})
    anh = anh[:_MAX_ANH]

    v = data.get("video")
    video = None
    if isinstance(v, dict) and str(v.get("chu_de", "")).strip():
        video = {"chu_de": str(v["chu_de"]).strip(),
                 "caption": str(v.get("caption", "")).strip() or "Video minh hoạ"}

    return {"khai_niem": str(data.get("khai_niem", "")).strip(), "vi_du": vi_du,
            "anh": anh, "video": video}


async def ingest_draft(session: AsyncSession, topic_id: int, *, nguon: str = "") -> dict:
    """Nháp bám SGK cho 1 đơn vị.

    Trả {khai_niem, vi_du, anh, video, trang_sgk, thieu_sgk, mon} — `anh`/`video`
    là ĐỀ XUẤT (prompt/chủ đề), việc sinh thật do app.lessons.media làm. `mon`
    trả kèm để caller đặt hàng video đúng kho SGK, không phải tra lại.
    """
    empty = {"khai_niem": "", "vi_du": [], "anh": [], "video": None,
             "trang_sgk": [], "thieu_sgk": True, "mon": None}
    topic = await session.get(CurriculumTopic, topic_id)
    if topic is None:
        return empty

    twins = list(await session.scalars(
        select(CurriculumTopic).filter_by(
            subject_id=topic.subject_id, grade_id=topic.grade_id,
            mach_noi_dung=topic.mach_noi_dung, don_vi_kien_thuc=topic.don_vi_kien_thuc,
        )
    ))
    ids = [t.id for t in twins] or [topic.id]
    cells = list(await session.scalars(select(BlueprintCell).where(BlueprintCell.topic_id.in_(ids))))
    ycd = list(dict.fromkeys(c.yeu_cau_can_dat for c in cells if c.yeu_cau_can_dat))

    # Truy vấn ghép đơn vị + mạch + yêu cầu cần đạt: payload Qdrant KHÔNG có
    # topic_id (cố ý — xem app/ingestion/chunking.py) nên không filter theo đơn vị
    # được, phải dựa vào độ tương đồng ngữ nghĩa của chính tên đơn vị + YCĐ.
    mon, khoi = await _mon_khoi(session, topic)
    chunks: list[RetrievedChunk] = []
    if mon and khoi:
        query = ". ".join([topic.don_vi_kien_thuc, topic.mach_noi_dung, *ycd])
        chunks = await retriever.retrieve(
            query, mon=mon, khoi=khoi, top_k=_TOP_K, score_threshold=_SCORE_THRESHOLD
        )
    thieu_sgk = not has_grounding(chunks)

    subject = await session.get(Subject, topic.subject_id)
    grade = await session.get(Grade, topic.grade_id)
    messages = [{"role": "user", "content": _prompt(
        topic.don_vi_kien_thuc, topic.mach_noi_dung,
        subject.name if subject else "Toán", grade.name if grade else "Lớp 6",
        ycd, nguon, _sgk_context(chunks),
    )}]
    # max_tokens rộng tay: model tầng mạnh là model REASONING, token suy luận ăn
    # CHUNG ngân sách này. Để 4096 thì phần trả lời thật chỉ còn vài trăm token và
    # bị cắt giữa chuỗi -> JSON hỏng -> nháp rỗng (đã gặp thật: output dừng ở
    # `($a \neq ` sau 1074 ký tự).
    raw = await gateway.complete(task="lesson_ingest", messages=messages, max_tokens=16384)
    draft = _parse(raw)

    # Đề xuất minh hoạ ở LẦN GỌI RIÊNG, và ground trên nội dung VỪA SOẠN chứ không
    # phải đoạn SGK thô — hình phải minh hoạ đúng bài học hiện ra màn hình.
    # Lỗi ở đây không được kéo sập nháp chữ (phần chính).
    try:
        media = await goi_y_media(topic.don_vi_kien_thuc, topic.mach_noi_dung, draft["khai_niem"])
    except LLMUnavailable:
        media = {"anh": [], "video": None}
    draft["anh"], draft["video"] = media["anh"], media["video"]

    draft["trang_sgk"] = sorted({c.page_no for c in chunks})
    draft["thieu_sgk"] = thieu_sgk
    draft["mon"] = mon
    return draft

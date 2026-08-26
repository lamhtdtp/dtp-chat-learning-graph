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
import re
import logging
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BlueprintCell, CurriculumTopic, Grade, Subject, TopicContent
from app.graph.grounding import has_grounding
from app.llm import gateway, jsonfix
from app.llm.gateway import LLMUnavailable
from app.retrieval import retriever
from app.retrieval.retriever import RetrievedChunk

log = logging.getLogger(__name__)

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
        '"vi_du": [{"de": "đề bài", "giai": "lời giải từng bước (HTML ngắn)", '
        '"anh_prompt": "<CHỈ khi ví dụ KHÔNG hiểu được nếu thiếu hình vẽ>"}]}\n'
        "Soạn 2–3 ví dụ từ dễ đến vận dụng.\n"
        "QUY TẮC HÌNH: ví dụ nào nhắc tới \"hình bên\", \"hình vẽ\", \"các hình sau\" hoặc "
        "là bài hình học cần quan sát thì PHẢI có `anh_prompt` — câu lệnh TIẾNG ANH tả "
        "hình cần vẽ, nền phẳng, phong cách sách giáo khoa, ghi rõ không có chữ/số trong "
        "hình. Nếu đề có ĐẶT TÊN điểm/đỉnh (M, N, P, ABC…) thì phải tả rõ từng "
        "chữ in hoa nằm cạnh điểm nào, font serif — thiếu nhãn là học sinh không "
        "gọi tên được đoạn thẳng. Ví dụ chỉ tính toán bằng số thì BỎ TRỐNG "
        "`anh_prompt`, đừng vẽ hình vô ích."
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
            v = {"de": str(e["de"]).strip(), "giai": str(e.get("giai", "")).strip()}
            # Ví dụ hình học không đọc được nếu thiếu hình. AI chỉ trả `anh_prompt`
            # cho ví dụ THẬT SỰ cần hình; sinh ảnh là việc riêng (mỗi ảnh 1 lần gọi
            # API, quota 50/ngày) nên để chuyên gia bấm, không sinh hàng loạt.
            if str(e.get("anh_prompt", "")).strip():
                v["anh_prompt"] = str(e["anh_prompt"]).strip()
            vi_du.append(v)

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


async def _yeu_cau_can_dat(session: AsyncSession, topic: CurriculumTopic
                           ) -> tuple[list[str], list[BlueprintCell]]:
    """(yêu cầu cần đạt đã khử trùng, cells) của đơn vị.

    Gom theo TẤT CẢ topic trùng tên trong cùng môn/khối ("twins"): mục lục khử
    trùng theo tên nên một đơn vị có thể ứng nhiều `topic_id`, chỉ lấy một cái là
    hụt yêu cầu cần đạt.
    """
    twins = list(await session.scalars(
        select(CurriculumTopic).filter_by(
            subject_id=topic.subject_id, grade_id=topic.grade_id,
            mach_noi_dung=topic.mach_noi_dung, don_vi_kien_thuc=topic.don_vi_kien_thuc,
        )
    ))
    ids = [t.id for t in twins] or [topic.id]
    cells = list(await session.scalars(select(BlueprintCell).where(BlueprintCell.topic_id.in_(ids))))
    return list(dict.fromkeys(c.yeu_cau_can_dat for c in cells if c.yeu_cau_can_dat)), cells


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

    ycd, cells = await _yeu_cau_can_dat(session, topic)

    # Truy vấn ghép đơn vị + mạch + yêu cầu cần đạt: payload Qdrant KHÔNG có
    # topic_id (cố ý — xem app/ingestion/chunking.py) nên không filter theo đơn vị
    # được, phải dựa vào độ tương đồng ngữ nghĩa của chính tên đơn vị + YCĐ.
    mon, khoi = await _mon_khoi(session, topic)
    chunks: list[RetrievedChunk] = []
    if mon and khoi:
        query = ". ".join([topic.don_vi_kien_thuc, topic.mach_noi_dung, *ycd])
        try:
            chunks = await retriever.retrieve(
                query, mon=mon, khoi=khoi, top_k=_TOP_K, score_threshold=_SCORE_THRESHOLD
            )
        except Exception:  # noqa: BLE001
            # Qdrant sập / chưa có collection / embedding lỗi -> COI NHƯ không có
            # ngữ liệu, không phải lỗi 500. Kho SGK hỏng thì chuyên gia vẫn phải
            # soạn bài được; cờ thieu_sgk sẽ nói rõ nháp này không bám sách.
            log.exception("Retrieve ngữ liệu SGK thất bại (topic=%s, mon=%s, khoi=%s)",
                          topic_id, mon, khoi)
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


# ── AI hỗ trợ theo TỪNG phần (REQ §2.2) ──────────────────────────────────────
# Mỗi phần có vai trò sư phạm khác nhau, nên prompt khác nhau. Dùng một prompt
# chung rồi chỉ đổi tên phần thì Khởi động ra y như Bài tập.
_YEU_CAU_PHAN = {
    "khoi_dong": ("Khởi động", "1–2 câu hỏi/tình huống gần gũi dẫn vào bài. KHÔNG dạy kiến thức mới, "
                               "KHÔNG đưa đáp án — mục đích chỉ là gợi tò mò."),
    "hoat_dong": ("Hoạt động", "1 hoạt động học sinh TỰ LÀM (cá nhân hoặc nhóm) để tự phát hiện ra "
                               "kiến thức. Ghi rõ các bước và câu hỏi chốt ở cuối."),
    "kien_thuc": ("Kiến thức trọng tâm", "Định nghĩa/tính chất cốt lõi, ngắn và chính xác. "
                                         "Dùng <blockquote> cho phần cần nhớ."),
    "luyen_tap": ("Luyện tập – Vận dụng", "3–4 bài từ nhận biết đến vận dụng, CÓ đáp số ngắn ở cuối "
                                          "mỗi bài. Tăng dần độ khó."),
    "bai_tap": ("Bài tập", "4–5 bài về nhà, đánh số <b>Bài n.</b> KHÔNG kèm lời giải — đây là bài "
                           "học sinh tự làm."),
}


# Dấu hiệu ví dụ PHẢI có hình mới đọc được. NGUỒN DUY NHẤT phía server — dùng cho
# cả sinh hàng loạt lẫn báo cáo. (Trình soạn CMS có bản TS riêng trong
# web-admin/src/admin/AnhViDu.tsx: sửa một bên nhớ sửa bên kia.)
CAN_HINH = re.compile(
    r"hình bên|hình vẽ|hình sau|các hình|quan sát hình|hình dưới|xem hình"
    r"|như hình|trên hình", re.IGNORECASE)


def can_hinh(e: dict) -> bool:
    """Ví dụ này nhắc tới hình mà chưa có hình?

    CHỈ xét ĐỀ BÀI, không xét lời giải. Lời giải hay tả hình dáng bằng lời nên
    quét nó là dương tính giả: ví dụ "chữ nào có tâm đối xứng: H, A, N, O, I"
    (không cần hình) bị gắn cờ vì lời giải có chữ "các hình" — vẽ ra là tốn một
    ảnh vô ích. Cần hình hay không là do ĐỀ hỏi gì.
    """
    if (e.get("anh") or "").strip():
        return False
    if (e.get("anh_prompt") or "").strip():
        return True
    return bool(CAN_HINH.search(e.get("de", "") or ""))


async def goi_y_hinh_vi_du(dv: str, mach: str, vi_du: list[dict]) -> dict[int, str]:
    """{chỉ số ví dụ: câu lệnh vẽ} cho các ví dụ cần hình mà chưa có `anh_prompt`.

    Một lời gọi TẦNG RẺ cho cả bài (không phải mỗi ví dụ một lời gọi): mô tả hình
    là việc ngắn, và ví dụ trong cùng bài dùng chung ngữ cảnh.
    """
    can = [(i, e) for i, e in enumerate(vi_du)
           if can_hinh(e) and not (e.get("anh_prompt") or "").strip()]
    if not can:
        return {}
    ds = "\n".join(f'{i}. {_bo_the_ngan(e.get("de", ""))}' for i, e in can)
    prompt = (
        f'Các ví dụ sau của bài "{dv}" (mạch "{mach}", Toán lớp 6) đều nhắc tới một '
        "hình vẽ. Với MỖI ví dụ, viết câu lệnh TIẾNG ANH tả hình cần vẽ.\n\n"
        f"{ds}\n\n"
        "Quy tắc: nền phẳng trắng, nét đen mảnh, phong cách sách giáo khoa, KHÔNG "
        "chữ trong hình — TRỪ khi đề đặt tên điểm/đường (A, B, m, n…) thì phải tả "
        "rõ từng chữ in hoa nằm cạnh đối tượng nào, font serif.\n"
        'Trả JSON: {"hinh": [{"idx": <số thứ tự ở trên>, "prompt": "..."}]}'
    )
    raw = await gateway.complete(task="media_suggest",
                                 messages=[{"role": "user", "content": prompt}],
                                 max_tokens=1024)
    d = jsonfix.boc_json(raw) or {}
    ra: dict[int, str] = {}
    for x in d.get("hinh", []) if isinstance(d.get("hinh"), list) else []:
        try:
            i = int(x["idx"])
        except (KeyError, TypeError, ValueError):
            continue
        pr = str(x.get("prompt", "")).strip()
        if pr and 0 <= i < len(vi_du):
            ra[i] = pr
    return ra


def _bo_the_ngan(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").strip()[:200]


async def soan_phan(session: AsyncSession, topic_id: int, phan: str) -> str:
    """HTML nháp cho MỘT phần, bám yêu cầu cần đạt. Trả "" nếu không soạn được."""
    topic = await session.get(CurriculumTopic, topic_id)
    if topic is None or phan not in _YEU_CAU_PHAN:
        return ""
    ten, yeu_cau = _YEU_CAU_PHAN[phan]
    ycd, _ = await _yeu_cau_can_dat(session, topic)
    content = await session.scalar(select(TopicContent).filter_by(topic_id=topic_id))
    # Grounding trên KIẾN THỨC đã soạn (nếu có): phần Luyện tập phải khớp đúng lý
    # thuyết trong bài, không phải kiến thức chung chung của mô hình.
    kt = (content.khai_niem if content else "") or ""

    prompt = (
        f'Soạn phần "{ten}" cho đơn vị kiến thức "{topic.don_vi_kien_thuc}" '
        f'(mạch "{topic.mach_noi_dung}"), môn Toán lớp 6.\n\n'
        + ("YÊU CẦU CẦN ĐẠT (bám sát):\n" + "\n".join(f"- {y}" for y in ycd) + "\n\n" if ycd else "")
        + (f"KIẾN THỨC TRỌNG TÂM ĐÃ SOẠN (phải khớp, không dạy khác đi):\n{kt}\n\n" if kt.strip() else "")
        + f"YÊU CẦU RIÊNG CỦA PHẦN NÀY: {yeu_cau}\n\n"
        "Trả về HTML THUẦN cho ĐÚNG phần này, không tiêu đề <h*>, không giải thích thêm. "
        "Công thức toán đặt trong $…$."
    )
    raw = await gateway.complete(
        task="lesson_ingest", messages=[{"role": "user", "content": prompt}], max_tokens=16384)
    html = raw.strip()
    # Model hay bọc trong ```html — bóc ra, nếu không chuyên gia thấy dấu ``` trong ô soạn.
    if html.startswith("```"):
        html = html.split("```")[1]
        html = html[4:].strip() if html.lower().startswith("html") else html.strip()
    return html

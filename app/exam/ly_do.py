"""Lý do từng phương án: vì sao đáp án này đúng, vì sao phương án kia sai.

Testbank hiện chỉ có MỘT `explanation` cho cả câu (team testbank đã xác nhận,
R3 chưa làm). Tạm thời mình sinh bằng AI — tầng rẻ, vì đáp án đúng và lời giải
gốc đã có trong tay, việc còn lại chỉ là DIỄN GIẢI cho từng phương án, không
phải giải lại bài.

Ràng buộc:
- Model KHÔNG tự quyết phương án nào đúng. Mình tính từ `answer_key` rồi nói
  thẳng trong prompt; model chỉ viết lý do cho kết luận đã có.
- Câu có HÌNH ở đề hoặc phương án thì không sinh: model chỉ thấy "[hình]", viết
  lý do cho thứ không nhìn thấy là bịa (ở kho Toán 6 thật, công thức phần lớn là
  ảnh — nên phần này thiếu nhiều, chấp nhận). Học sinh vẫn có lời giải gốc.
- Phương án nào model trả thiếu thì BỎ dòng đó, không vá tạm (cùng lối với
  `app/lessons/quiz.py::_parse_quiz`).
- Sinh SẴN lúc rút đề, cache theo (qid, version) dùng chung mọi học sinh. Sinh
  lúc nộp thì học sinh ngồi chờ hàng chục lượt gọi model.
- Model chết / hết quota: bỏ qua. Lý do là phần phụ, không được làm hỏng đề.

Khi testbank có `rationale` theo `option_key` (C2): ghi vào `ly_do_phuong_an`
với `nguon="testbank"` — hàm đọc ở đây ưu tiên nguồn đó, frontend không đổi gì.
"""
import asyncio
import logging

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LyDoPhuongAn
from app.integrations.testbank.cham import tach_khoa
from app.integrations.testbank.hien_thi import co_anh, sang_van_ban
from app.llm import gateway, jsonfix
from app.llm.gateway import LLMUnavailable

log = logging.getLogger(__name__)

_DANG_CO_PHUONG_AN = {"TN1", "TNN", "DS"}
#: Thứ tự ưu tiên nguồn: bản có người duyệt của testbank đứng trước bản AI.
_UU_TIEN = {"testbank": 0, "ai": 1}
#: Gọi model song song có giới hạn — 12 câu một lượt mà bắn cả 12 cùng lúc thì
#: dễ ăn 429 của provider (VNGCloud giới hạn chặt).
_SONG_SONG = 4


def dung_sai(cau: dict) -> dict[str, bool]:
    """Phương án nào đúng. TN1/TNN: khoá có trong `answer_key`. DS: ý thứ i đúng
    khi phần tử thứ i của `answer_key` là Đ (chấp nhận cả `D` không dấu)."""
    keys = [o["key"] for o in cau.get("options") or []]
    if cau.get("format_code") == "DS":
        y = [p.strip().upper() for p in (cau.get("answer_key") or "").replace(";", ",").split(",")]
        return {k: i < len(y) and y[i] in ("Đ", "D") for i, k in enumerate(keys)}
    dung = set(tach_khoa(cau.get("answer_key")))
    return {k: k.upper() in dung for k in keys}


def can_sinh(cau: dict) -> bool:
    opts = cau.get("options") or []
    return (cau.get("format_code") in _DANG_CO_PHUONG_AN and len(opts) >= 2
            and bool((cau.get("answer_key") or "").strip())
            and not co_anh(cau.get("stem")) and not co_anh(cau.get("stimulus"))
            and not any(co_anh(o.get("text")) for o in opts))


def tao_prompt(cau: dict) -> str:
    ds = cau.get("format_code") == "DS"
    ds_dung = dung_sai(cau)
    dong = "\n".join(
        f"{o['key']}. {sang_van_ban(o.get('text'))} — "
        + ("ĐÚNG" if ds_dung[o["key"]] else "SAI")
        for o in cau["options"])
    loai = ("Mỗi dòng là một KHẲNG ĐỊNH, đã ghi sẵn khẳng định đó đúng hay sai."
            if ds else "Đã ghi sẵn phương án nào ĐÚNG, phương án nào SAI.")
    return f"""Em là giáo viên Toán lớp 6. Viết lý do ngắn cho TỪNG phương án của câu hỏi dưới đây.

{loai} KHÔNG được đổi kết luận đúng/sai đó.
- Phương án ĐÚNG: giải thích vì sao đúng.
- Phương án SAI: chỉ ra học sinh chọn nó thường nhầm ở đâu, và vì sao sai.
Mỗi lý do 1–2 câu, xưng "em" với học sinh, bám lời giải gốc, không thêm kiến thức ngoài lớp 6.
Chỗ ghi [hình] là hình không đọc được — đừng đoán nội dung của nó.

CÂU HỎI:
{sang_van_ban(cau.get('stimulus'))}
{sang_van_ban(cau.get('stem'))}

CÁC PHƯƠNG ÁN:
{dong}

LỜI GIẢI GỐC:
{sang_van_ban(cau.get('explanation')) or '(không có)'}

Chỉ trả về JSON, khoá là chữ cái phương án, ví dụ: {{"A": "…", "B": "…"}}"""


def boc_ly_do(raw: str, keys: list[str]) -> dict[str, str]:
    data = jsonfix.boc_json(raw)
    if not isinstance(data, dict):
        return {}
    return {k: str(data[k]).strip() for k in keys
            if isinstance(data.get(k), (str, int, float)) and str(data[k]).strip()}


async def _sinh(cau: dict, khoa: asyncio.Semaphore) -> dict[str, str]:
    async with khoa:
        try:
            raw = await gateway.complete(
                "rationale_gen", [{"role": "user", "content": tao_prompt(cau)}], max_tokens=1500)
        except LLMUnavailable as exc:
            log.warning("Không sinh được lý do cho %s (%s) — bỏ qua", cau.get("qid"), exc)
            return {}
    return boc_ly_do(raw, [o["key"] for o in cau["options"]])


async def _doc(session: AsyncSession, caus: list[dict]) -> dict[str, dict[str, dict]]:
    cap = {(c["qid"], c.get("version") or "") for c in caus}
    if not cap:
        return {}
    rows = (await session.scalars(
        select(LyDoPhuongAn).where(tuple_(LyDoPhuongAn.qid, LyDoPhuongAn.version).in_(cap))
    )).all()
    out: dict[str, dict[str, dict]] = {}
    for r in sorted(rows, key=lambda r: _UU_TIEN.get(r.nguon, 9)):
        # Đã có nguồn ưu tiên hơn cho phương án này thì giữ, bỏ bản sau.
        out.setdefault(r.qid, {}).setdefault(
            r.option_key, {"noi_dung": r.noi_dung, "nguon": r.nguon})
    return out


async def _da_sinh_ai(session: AsyncSession, caus: list[dict]) -> set[tuple[str, str]]:
    cap = {(c["qid"], c.get("version") or "") for c in caus}
    if not cap:
        return set()
    return set((await session.execute(
        select(LyDoPhuongAn.qid, LyDoPhuongAn.version).distinct()
        .where(LyDoPhuongAn.nguon == "ai",
               tuple_(LyDoPhuongAn.qid, LyDoPhuongAn.version).in_(cap)))).all())


async def dam_bao_ly_do(session: AsyncSession, caus: list[dict]) -> dict[str, dict[str, dict]]:
    """qid -> option_key -> {noi_dung, nguon}. Đọc cache; câu nào CHƯA có dòng
    nào thì sinh (song song có giới hạn) rồi lưu. Không commit — chỗ gọi commit
    cùng giao dịch lưu đề."""
    co = await _doc(session, caus)
    da_sinh = await _da_sinh_ai(session, caus)
    # Sinh khi còn phương án thiếu lý do VÀ chưa từng sinh bản AI cho đúng phiên
    # bản này. Vế sau chặn gọi model lặp mãi cho câu mà model cứ bỏ sót một
    # phương án — lần đầu thiếu thì chấp nhận thiếu.
    can = [c for c in caus
           if can_sinh(c) and (c["qid"], c.get("version") or "") not in da_sinh
           and any(o["key"] not in co.get(c["qid"], {}) for o in c["options"])]
    if can:
        khoa = asyncio.Semaphore(_SONG_SONG)
        moi = await asyncio.gather(*(_sinh(c, khoa) for c in can))
        dong = [{"qid": c["qid"], "version": c.get("version") or "", "option_key": k,
                 "noi_dung": v, "nguon": "ai"}
                for c, ld in zip(can, moi) for k, v in ld.items()]
        if dong:
            # Hai học sinh rút trúng cùng câu cùng lúc -> cả hai cùng sinh. Bản
            # nào ghi trước thì giữ, bản sau bỏ — không nổ unique.
            await session.execute(insert(LyDoPhuongAn).values(dong).on_conflict_do_nothing())
            co = await _doc(session, caus)
    return co

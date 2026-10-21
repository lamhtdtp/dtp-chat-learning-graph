"""Lý do từng phương án cho bài theo mã Testbank, theo NỘI DUNG CÂU TRÊN TỜ ĐỀ (US-30 KB 16, 18, 19).

Vì sao không dùng thẳng `app/exam/ly_do.py` (khoá theo mã câu + phiên bản): thầy cô sửa riêng câu
cho tờ đề được — đáp án, một phương án, số liệu — mà mã câu và phiên bản vẫn là của kho. Lý do của
kho khi ấy nói NGƯỢC đáp án của tờ đề, đúng loại sai mà học sinh tin nhất vì nó nằm ngay dưới đáp án.
Nên khoá ở đây là DẤU VÂN nội dung (`dau_van`): hai lượt phát cùng nội dung dùng chung một lần sinh,
nội dung khác thì sinh riêng.

Ba quy tắc:
- Đọc lý do chỉ là đọc DB (không gọi model, không chặn việc xem đáp án). Câu chưa có thì lên lịch sinh
  NỀN (`sinh_nen`) và hiện "đang chuẩn bị"; mở lại sau là thấy.
- Nội dung tờ đề trùng nội dung kho và kho đã có lý do cho (mã câu, phiên bản) đó (từ đề tự sinh) thì
  CHÉP lại, không gọi model. Phải so nội dung với kho (một lần gọi `questions:resolve`) chứ không tin
  mã câu + phiên bản — đó chính là chỗ thầy cô sửa mà không đổi số.
- Model chết -> không đánh dấu "đã sinh", lần mở sau thử lại. Model trả thiếu phương án -> thiếu
  thì để thiếu, không bịa, không gọi lại (cùng lối với `ly_do.dam_bao_ly_do`).
"""
import asyncio
import hashlib
import json
import logging
from contextlib import AbstractAsyncContextManager

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LyDoToDe
from app.db.session import async_session_factory
from app.exam import ly_do as ly_do_svc
from app.integrations.testbank.client import TestbankClient
from app.integrations.testbank.noi_dung import lay_cau

log = logging.getLogger(__name__)

MSG_DANG_CHUAN_BI = "Đang chuẩn bị giải thích từng phương án, em mở lại sau ít phút"
#: Chờ kho trả nội dung để so với tờ đề tối đa chừng này — quá thì coi như không chép được, sinh mới.
_HAN_KHO_GIAY = 3
_SONG_SONG = 4


def mo_session() -> AbstractAsyncContextManager[AsyncSession]:
    """Phiên DB riêng cho việc sinh nền (phiên của request đã đóng khi tác vụ nền chạy). Test thay."""
    return async_session_factory()


def _gon(t: str | None) -> str:
    return " ".join((t or "").split())


def cau_kieu_kho(c: dict) -> dict:
    """Câu đã chép từ chi tiết sau nộp -> dạng câu của kho mà `ly_do.py` hiểu (stem / options / ...)."""
    return {
        "qid": c.get("qid") or "", "version": c.get("phien_ban") or "", "format_code": c["dang"],
        "stem": c.get("de_bai") or "", "stimulus": c.get("khoi_du_kien") or "",
        "options": [{"key": p["khoa"], "label": p.get("nhan") or p["khoa"], "text": p.get("noi_dung") or ""}
                    for p in c.get("phuong_an") or []],
        "answer_key": c.get("dap_an") or "", "explanation": c.get("bai_giai") or "",
        # Đáp án này CHÍNH LÀ của kho (đã đối chiếu nội dung với kho lúc lấy): khỏi gọi kho so lại.
        "_tu_kho": bool(c.get("_tu_kho")),
    }


def dau_van(cau: dict) -> str:
    """Dấu vân NỘI DUNG câu (dạng kho): đúng những thứ `ly_do.tao_prompt` đưa cho model — đổi một
    trong chúng là lý do cũ có thể sai. Khoảng trắng thừa không tính; nhãn hiển thị (a, b…) không tính."""
    goc = {
        "d": cau.get("format_code") or "", "s": _gon(cau.get("stem")), "k": _gon(cau.get("stimulus")),
        "o": [[o["key"], _gon(o.get("text"))] for o in cau.get("options") or []],
        "a": "".join((cau.get("answer_key") or "").split()), "g": _gon(cau.get("explanation")),
    }
    return hashlib.sha256(json.dumps(goc, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


async def _chep_tu_kho(session: AsyncSession, tb: TestbankClient, can: dict[str, dict]) -> None:
    """`can`: dấu vân -> câu (dạng kho) chưa có lý do theo tờ đề. Câu nào nội dung TRÙNG nội dung kho và
    kho đã có lý do cho (mã câu, phiên bản) thì chép sang `ly_do_to_de`. Lỗi kho -> bỏ qua (sẽ sinh mới)."""
    cap = {(c["qid"], c["version"]) for c in can.values() if c["qid"]}
    if not cap:
        return
    cu = await ly_do_svc._doc(session, [{"qid": q, "version": v} for q, v in cap])
    if not cu:
        return
    cho_so = {q for q, _ in cap if q in cu and any(
        not c["_tu_kho"] and c["qid"] == q for c in can.values())}
    theo_qid: dict[str, dict] = {}
    if cho_so:
        try:
            async with asyncio.timeout(_HAN_KHO_GIAY):
                kho = await lay_cau(tb, sorted(cho_so))
        except Exception as e:  # noqa: BLE001 — kho chậm / chết: không chép được, để sinh mới
            log.warning("Không lấy được nội dung kho để so với tờ đề (%s)", type(e).__name__)
            return
        theo_qid = {k["qid"]: k for k in kho}
    dong = []
    for h, c in can.items():
        if not c["_tu_kho"]:
            k = theo_qid.get(c["qid"])
            if k is None or (k.get("version") or "") != c["version"] or dau_van(k) != h:
                continue                   # tờ đề đã bị sửa so với kho (hoặc khác phiên bản): KHÔNG dùng
        elif c["qid"] not in cu:
            continue
        for key, v in (cu.get(c["qid"]) or {}).items():
            dong.append({"noi_dung_hash": h, "option_key": key, "noi_dung": v["noi_dung"], "nguon": "kho"})
        dong.append({"noi_dung_hash": h, "option_key": "", "noi_dung": "", "nguon": "kho"})
    if dong:
        await session.execute(insert(LyDoToDe).values(dong).on_conflict_do_nothing())


async def doc_ly_do(session: AsyncSession, tb: TestbankClient | None, caus: list[dict]
                    ) -> tuple[dict[int, dict], list[tuple[str, dict]]]:
    """`caus`: các câu đã chép (có `stt`, `dang`, `de_bai`, `phuong_an`, `dap_an`, `bai_giai`…) của MỘT
    bài đã được phép xem đáp án. Trả:
    - `{stt: {"ly_do": {khoá: nội dung}, "trang_thai": "co" | "dang_chuan_bi" | "khong"}}`
    - việc cần sinh nền `[(dấu vân, câu dạng kho)]` (chỗ gọi lên lịch `sinh_nen`).

    "khong" = câu không có lý do theo phương án (có hình, tự luận, đáp số…) hoặc đã sinh mà model không
    dùng được — giao diện chỉ hiện đáp án + lời giải, không nói gì thêm."""
    kho_cau = {c["stt"]: cau_kieu_kho(c) for c in caus if ly_do_svc.can_sinh(cau_kieu_kho(c))}
    hash_cua = {stt: dau_van(c) for stt, c in kho_cau.items()}
    out: dict[int, dict] = {c["stt"]: {"ly_do": {}, "trang_thai": "khong"} for c in caus}
    if not kho_cau:
        return out, []

    async def doc() -> tuple[dict[str, dict[str, str]], set[str]]:
        rows = (await session.scalars(
            select(LyDoToDe).where(LyDoToDe.noi_dung_hash.in_(set(hash_cua.values()))))).all()
        co: dict[str, dict[str, str]] = {}
        da_sinh: set[str] = set()
        for r in rows:
            if r.option_key == "":
                da_sinh.add(r.noi_dung_hash)
            else:
                co.setdefault(r.noi_dung_hash, {})[r.option_key] = r.noi_dung
        return co, da_sinh

    co, da_sinh = await doc()
    chua = {h: kho_cau[s] for s, h in hash_cua.items() if h not in da_sinh}
    if chua and (tb is not None or any(c["_tu_kho"] for c in chua.values())):
        await _chep_tu_kho(session, tb, chua)
        co, da_sinh = await doc()

    viec: dict[str, dict] = {}
    for stt, h in hash_cua.items():
        keys = [o["key"] for o in kho_cau[stt]["options"]]
        ly = {k: co.get(h, {}).get(k, "") for k in keys}
        ly = {k: v for k, v in ly.items() if v.strip()}
        if h in da_sinh:
            out[stt] = {"ly_do": ly, "trang_thai": "co" if ly else "khong"}
        else:
            out[stt] = {"ly_do": ly, "trang_thai": "dang_chuan_bi"}
            viec.setdefault(h, kho_cau[stt])
    return out, list(viec.items())


async def _sinh_mot(h: str, cau: dict, khoa: asyncio.Semaphore) -> None:
    try:
        async with khoa, mo_session() as s:
            # Khoá cố vấn tới hết giao dịch: 30 học sinh cùng mở một lúc thì chỉ một bên sinh, bên kia
            # bỏ qua (lần mở sau thấy kết quả) — "tối đa một lần cho mỗi nội dung câu".
            lay_duoc = await s.scalar(select(func.pg_try_advisory_xact_lock(
                func.hashtextextended(f"lydo:{h}", 0))))
            if not lay_duoc:
                return
            if await s.scalar(select(LyDoToDe.id).where(
                    LyDoToDe.noi_dung_hash == h, LyDoToDe.option_key == "").limit(1)):
                return
            ly = await ly_do_svc.sinh_ly_do(cau)
            if ly is None:                 # model không trả lời: chưa "đã sinh", lần mở sau thử lại
                return
            dong = [{"noi_dung_hash": h, "option_key": k, "noi_dung": v, "nguon": "ai"} for k, v in ly.items()]
            dong.append({"noi_dung_hash": h, "option_key": "", "noi_dung": "", "nguon": "ai"})
            await s.execute(insert(LyDoToDe).values(dong).on_conflict_do_nothing())
            await s.commit()
    except Exception:  # noqa: BLE001 — việc nền: lỗi không được làm hỏng gì, nhưng phải thấy trong log
        log.exception("Sinh lý do theo tờ đề lỗi")


async def sinh_nen(viec: list[tuple[str, dict]]) -> None:
    """Sinh lý do cho các câu chưa có, chạy SAU khi đã trả bài cho học sinh (BackgroundTasks)."""
    khoa = asyncio.Semaphore(_SONG_SONG)
    await asyncio.gather(*(_sinh_mot(h, c, khoa) for h, c in viec))

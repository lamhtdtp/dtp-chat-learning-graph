"""Đáp án / lời giải của câu trên tờ đề thầy cô giao, lấy từ KHO Testbank ngay sau khi nộp (US-30, quyết định
mới của chủ sản phẩm: đề giao hiện đáp án giống đề tự sinh, không chờ thầy cô đóng bài).

Testbank che đáp án của tờ đề tới khi thầy cô đóng lượt (`chi-tiet` trả `dap_an=None`), nên learning tự lấy
đáp án của kho qua `questions:resolve` (tài khoản dịch vụ) theo (mã câu, phiên bản) của câu trên tờ đề. Kho
KHÔNG phải tờ đề: thầy cô sửa riêng câu cho tờ đề được (đáp án, một phương án, số liệu) mà mã câu và phiên bản
vẫn của kho — hiện đáp án kho cho câu như vậy là nói NGƯỢC đáp án thầy cô, nên có hai rào, câu vướng rào thì
KHÔNG hiện đáp án kho (kết quả `t` khác "ok"):

  "sua"  nội dung trên tờ đề (đề bài, dữ kiện, phương án, dạng) khác nội dung kho sau khi chuẩn hoá khoảng trắng,
         hoặc tờ đề thiếu mã câu / phiên bản, hoặc kho đã sang phiên bản khác (kho chỉ trả bản hiện hành);
  "lech" chấm lại bài làm của em bằng đáp án kho ra Đúng/Sai KHÁC kết quả Testbank đã chấm — dấu hiệu thầy cô
         đổi đáp án mà không đổi chữ. Điểm vẫn là điểm của Testbank, đây chỉ là chặn hiện đáp án sai.

Hạn chế đã biết (không phát hiện được): thầy cô đổi đáp án mà bài làm của em sai ở CẢ hai đáp án thì hai bên
vẫn cùng chấm "Sai", không có gì để so — Testbank giấu đáp án của tờ đề tới khi đóng lượt.

Bản chép lưu trong `de_cuoi_ky.chi_tiet_json` (từng câu có khoá `kho`) để mở lại không gọi kho nữa; thêm bộ nhớ
đệm trong tiến trình theo (mã câu, phiên bản) cho nhiều học sinh cùng một tờ đề — cặp này bất biến (sửa câu
là sang phiên bản mới).
"""
import asyncio
import logging
from collections import OrderedDict

from app.integrations.testbank import cham as cham_svc
from app.integrations.testbank.client import TestbankClient
from app.integrations.testbank.noi_dung import lay_cau

log = logging.getLogger(__name__)

MSG_DA_CHINH = "Câu này thầy cô đã chỉnh, đáp án sẽ có khi thầy cô chữa bài"
OK, SUA, LECH = "ok", "sua", "lech"
#: Chờ kho tối đa chừng này giây: quá thì coi như chưa lấy được, lần hỏi sau thử lại (không chặn việc xem kết quả).
HAN_KHO_GIAY = 8
_TU_CHAM = ("DUNG", "SAI", "DUNG_MOT_PHAN")
_TOI_DA_CACHE = 2000
_cache: "OrderedDict[tuple[str, str], dict]" = OrderedDict()


def xoa_cache() -> None:
    _cache.clear()


def _gon(t: str | None) -> str:
    return " ".join((t or "").split())


def _pa(dang: str, cap: list[tuple[str, str]]) -> tuple:
    """Phương án để so. Dạng DS: Testbank phát đề ĐÁNH SỐ LẠI khoá ý ("1", "2"…) còn kho giữ "A", "B"… (đã gặp
    thật ở bản Testbank local) — so theo thứ tự + chữ, không so khoá. Dạng khác so cả khoá."""
    return tuple(t for _k, t in cap) if dang == "DS" else tuple(cap)


def _van_to_de(c: dict) -> tuple:
    return (c["dang"], _gon(c.get("de_bai")), _gon(c.get("khoi_du_kien")), _gon(c.get("dan_khoi_du_kien")),
            _pa(c["dang"], [(p["khoa"], _gon(p.get("noi_dung"))) for p in c.get("phuong_an") or []]))


def _van_kho(k: dict) -> tuple:
    dang = k.get("format_code") or ""
    return (dang, _gon(k.get("stem")), _gon(k.get("stimulus")), _gon(k.get("stimulus_lead")),
            _pa(dang, [(o["key"], _gon(o.get("text"))) for o in k.get("options") or []]))


def _nho(k: dict) -> None:
    _cache[(k["qid"], k.get("version") or "")] = k
    _cache.move_to_end((k["qid"], k.get("version") or ""))
    while len(_cache) > _TOI_DA_CACHE:
        _cache.popitem(last=False)


async def _tai_kho(tb: TestbankClient, qids: list[str]) -> None:
    async with asyncio.timeout(HAN_KHO_GIAY):
        for k in await lay_cau(tb, qids, include_answers=True):
            _nho(k)


def _quyet_dinh(c: dict, k: dict | None, chon: str, hs_id: object) -> dict:
    if k is None or (k.get("version") or "") != (c.get("phien_ban") or "") or _van_kho(k) != _van_to_de(c):
        return {"t": SUA}
    dap_an = k.get("answer_key") or ""
    if c["dang"] != "TL" and c.get("trang_thai") in _TU_CHAM:
        kc = cham_svc.cham(c["dang"], dap_an, chon)
        if not kc.cham_duoc or kc.dung != (c["trang_thai"] == "DUNG"):
            # Không log đáp án / bài làm — chỉ đủ để người vận hành tìm lại bài.
            log.warning("CANH_BAO testbank_cham_lech de=%s stt=%s", hs_id, c["stt"])
            return {"t": LECH}
    return {"t": OK, "dap_an": dap_an, "bai_giai": k.get("explanation") or "",
            "anh": dict(k.get("assets") or {}), "anh_co": dict(k.get("asset_sizes") or {})}


async def bo_sung(tb: TestbankClient | None, cau: list[dict], chon_theo_stt: dict[int, str], *,
                  nhan_bai: object = "") -> None:
    """Điền khoá `kho` cho các câu CHƯA có (câu đã có — kể cả bị rào — giữ nguyên, quyết định đó là cuối cùng).
    Sửa `cau` tại chỗ. Kho chết / chậm -> để nguyên (không ném lỗi), lần hỏi sau thử lại. `nhan_bai` chỉ để log."""
    chua = [c for c in cau if "kho" not in c]
    for c in chua:
        if not (c.get("qid") and c.get("phien_ban")):
            c["kho"] = {"t": SUA}
    can = [c for c in chua if "kho" not in c]
    if not can:
        return
    thieu = sorted({c["qid"] for c in can if (c["qid"], c["phien_ban"]) not in _cache})
    if thieu:
        if tb is None:
            return
        try:
            await _tai_kho(tb, thieu)
        except Exception as e:  # noqa: BLE001 — kho chậm / chết / token: bài vẫn xem được, chưa có đáp án
            log.warning("Không lấy được đáp án kho cho bài theo mã (%s)", type(e).__name__)
            return
    kho_theo_qid = {q: k for (q, _v), k in _cache.items()}
    for c in can:
        k = _cache.get((c["qid"], c["phien_ban"])) or kho_theo_qid.get(c["qid"])
        c["kho"] = _quyet_dinh(c, k, chon_theo_stt.get(c["stt"], ""), nhan_bai)

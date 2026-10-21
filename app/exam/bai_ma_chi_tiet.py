"""Chi tiết sau nộp của bài theo mã Testbank mức 1 (US-30): kết quả theo YCCĐ + Đề xuất ngay sau
nộp (giai đoạn 1), đáp án + lời giải + lý do từng phương án khi thầy cô đã đóng lượt (giai đoạn 2).

Luồng dữ liệu một chiều: Testbank `GET /doi-tac/bai-lam/{id}/chi-tiet` -> `chep_chi_tiet` (bản chép
trong `de_cuoi_ky.chi_tiet_json`) -> `dung_ket_qua` (dựng phản hồi cho trình duyệt). Mọi thứ trình duyệt
nhận đều đi qua `dung_ket_qua`, và nó chỉ đưa đáp án / lời giải / lý do ra khi CỜ CỦA CHÍNH BÀI NÀY
(`dap_an_mo`, lấy từ Testbank) bật — không bao giờ dựa vào chuyện learning "có sẵn" dữ liệu (kho,
bộ nhớ đệm, bài của lượt phát khác cùng nội dung): phần đó KB 22 cấm.

Thời điểm hỏi Testbank (không bao giờ ở nền, không định kỳ):
  nộp xong · nhận ra bài đã bị tự nộp · học sinh mở lại một bài chưa có đáp án.
Mỗi bài tối đa một lần mỗi 60 giây (`HAN_DOC_LAI_GIAY`, đếm bằng đồng hồ Postgres nên nhiều tab /
replica dùng chung). Bài đã có đáp án hoặc đã quá hạn thì không bao giờ hỏi lại.
"""
import json
import logging

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import cuoi_ky as ck
from app.config import settings
from app.db.models import DeCuoiKy, QuizAttempt, QuizAttemptItem
from app.exam import ly_do as ly_do_svc
from app.exam import ly_do_to_de
from app.integrations.testbank import cham as cham_svc
from app.integrations.testbank import delivery as dl_mod
from app.integrations.testbank.client import TestbankClient
from app.integrations.testbank.delivery import DeliveryLoi
from app.integrations.testbank.doi_tac import DoiTacClient, MA_KHONG_THAY_BAI
from app.integrations.testbank.hien_thi import _DAU_ANH, sang_html
from app.lessons import de_xuat as de_xuat_svc
from app.lessons.ycd_key import chuan_hoa

log = logging.getLogger(__name__)

#: Một bài chỉ bị hỏi Testbank nhiều nhất một lần trong chừng này giây (KB 15). Test chỉnh được.
HAN_DOC_LAI_GIAY = 60
_NGUONG_DAT = 0.7

MSG_CHO_DONG = "Đáp án và giải thích sẽ mở khi thầy cô đóng bài"
MSG_DA_DONG = "Thầy cô đã đóng bài — em xem đáp án và giải thích bên dưới"
MSG_QUA_HAN = "Bài đã quá hạn mở đáp án, em hỏi lại thầy cô nhé"
MSG_CHUA_KIEM = "Chưa kiểm tra được thầy cô đã đóng bài chưa, em thử lại sau ít phút"
MSG_DANG_CHUAN_BI = "Đang chuẩn bị kết quả theo yêu cầu cần đạt, em mở lại bài sau ít phút"

#: Kết quả của một lần thử lấy chi tiết (`thu_chi_tiet`).
TAT = "tat"              # cờ "lấy chi tiết sau nộp" tắt
KHONG_CAN = "khong_can"  # đã có đáp án / vừa hỏi chưa tới 60 giây: dùng bản chép
OK = "ok"
LOI_TAM = "loi_tam"      # Testbank không trả lời / 5xx / token / cấu hình
KHONG_DUONG = "khong_duong"   # 404 không phải "không thấy bài": Testbank chưa có đường chi tiết
MAT_BAI = "mat_bai"      # 404 KHONG_TIM_THAY_BAI_LAM
HET_HAN = "het_han"      # 410 quá hạn xem lại

_TRANG_THAI_CHAM = {"DUNG": "Đúng", "SAI": "Sai", "DUNG_MOT_PHAN": "Đúng một phần",
                    "CHO_GIAO_VIEN_CHAM": "Chưa chấm"}
_TU_CHAM = ("DUNG", "SAI", "DUNG_MOT_PHAN")


# ── Bản chép ────────────────────────────────────────────────────────────────
def _id_anh_hien_thi(c: dict) -> set[str]:
    """Id ảnh nằm trong phần HỌC SINH ĐƯỢC THẤY (đề bài, phương án, dữ kiện) — như Testbank lọc."""
    mau = [c.get("de_bai"), c.get("khoi_du_kien"), c.get("dan_khoi_du_kien"),
           *(p.get("noi_dung") for p in c.get("phuong_an") or [])]
    return {m.group(1) for t in mau for m in _DAU_ANH.finditer(t or "")}


def chep_cau(c: dict, hien: bool) -> dict:
    """Một `CauKetQuaGv` của Testbank -> bản chép. Đáp án + lời giải CHỈ khi `hien` (cờ của Testbank):
    Testbank đã che, nhưng bản chép tự che nữa — không tin bên kia làm đúng, vì lỗi này là lộ đáp án."""
    anh, anh_co = dict(c.get("anh") or {}), dict(c.get("anh_co") or {})
    if not hien:
        ids = _id_anh_hien_thi(c)
        anh, anh_co = {i: u for i, u in anh.items() if i in ids}, {i: u for i, u in anh_co.items() if i in ids}
    return {
        "stt": c["so_thu_tu"], "qid": c.get("qid") or "", "phien_ban": c.get("phien_ban") or "",
        "ma_hien_thi": c.get("ma_hien_thi") or "", "ar_id": c.get("ar_id") or "",
        "ycd": (c.get("yccd") or "").strip(), "muc_do": c.get("muc_do") or "", "dang": c["dang"],
        "de_bai": c.get("de_bai") or "", "khoi_du_kien": c.get("khoi_du_kien") or "",
        "dan_khoi_du_kien": c.get("dan_khoi_du_kien") or "",
        "phuong_an": [{"khoa": p["khoa"], "nhan": p.get("nhan") or p["khoa"], "noi_dung": p.get("noi_dung") or ""}
                      for p in c.get("phuong_an") or []],
        "trang_thai": c.get("trang_thai"), "diem": c.get("diem"), "diem_toi_da": c.get("diem_toi_da"),
        "anh": anh, "anh_co": anh_co,
        "dap_an": (c.get("dap_an") or "") if hien else None,
        "bai_giai": (c.get("bai_giai") or "") if hien else None,
    }


def _cham_duoc(c: dict) -> bool:
    """Câu chấm tự động: không phải tự luận và Testbank đã chấm. Câu tự luận KHÔNG tính (KB 9), kể cả
    khi thầy cô đã chấm trước lúc learning chép."""
    return c["dang"] != "TL" and c.get("trang_thai") in _TU_CHAM


async def _ghi_thong_ke(session: AsyncSession, row: DeCuoiKy, cau: list[dict],
                        ban_do: dict[str, tuple[int, str]]) -> None:
    """Một lần nộp vào thống kê YCCĐ, ĐÚNG MỘT LẦN cho mỗi bài: `attempt_id` là dấu "đã ghi" (cập nhật
    trong cùng giao dịch, dưới khoá hàng). Đúng một phần = chưa đúng. Không ghi đáp án (giai đoạn 1
    chưa có, và thống kê không cần)."""
    if row.attempt_id:
        return
    cham = [c for c in cau if _cham_duoc(c)]
    diem = sum(1 for c in cham if c["trang_thai"] == "DUNG")
    at = QuizAttempt(user_id=row.user_id, topic_id=None, diem=diem, tong=len(cham),
                     dat=bool(cham) and diem / len(cham) >= _NGUONG_DAT, nguon="de_giao")
    session.add(at)
    await session.flush()
    da_chon = json.loads(row.tra_loi_json or "{}")
    khong_khop = set()
    for c in cham:
        tid, _dv = ban_do.get(chuan_hoa(c["ycd"]), (None, ""))
        if tid is None:
            khong_khop.add(c["ar_id"] or c["ycd"])
        session.add(QuizAttemptItem(
            attempt_id=at.id, ycd_key=chuan_hoa(c["ycd"]), ycd_text=c["ycd"], ar_id=c["ar_id"] or None,
            qid=c["qid"] or None, phan="kien_thuc" if tid else "", muc_do=c["muc_do"],
            chon=da_chon.get(dl_mod.qid_cau(c["stt"]), ""), dap_an="", dung=c["trang_thai"] == "DUNG"))
    row.attempt_id = at.id
    if khong_khop and ban_do:
        # Không đoán theo độ giống: gắn sai bài mà không ai biết còn tệ hơn không gắn (US-27 KB 20).
        log.error("YCCĐ testbank không khớp ma trận của mình (không đoán): %s", sorted(khong_khop))
    await session.flush()


async def chep_chi_tiet(session: AsyncSession, row: DeCuoiKy, ct: dict) -> None:
    """Chép chi tiết Testbank vừa trả vào bài + ghi thống kê (một lần). Chưa commit."""
    hien = bool(ct.get("hien_dap_an_cho_hoc_sinh"))
    cau = [chep_cau(c, hien) for c in ct.get("cau") or []]
    row.chi_tiet_json = json.dumps({"cau": cau}, ensure_ascii=False)
    if hien:
        row.dap_an_mo = True
    if json.loads(row.cau_json or "[]") == []:
        # Vào lại bài đã bị tự nộp từ lúc learning chưa có bản chép câu: dựng câu từ chi tiết.
        goc = settings.testbank_content_url
        row.cau_json = json.dumps([dl_mod.cau_cong_khai({**c, "so_thu_tu": c["stt"]}, goc) for c in cau],
                                  ensure_ascii=False)
    await _ghi_thong_ke(session, row, cau, await ck._ban_do_yccd(session, de_xuat_svc.TB_MON, de_xuat_svc.TB_LOP))


# ── Hỏi Testbank ────────────────────────────────────────────────────────────
async def _vua_hoi(session: AsyncSession, row: DeCuoiKy) -> bool:
    return bool(await session.scalar(text(
        "SELECT kiem_luc IS NOT NULL AND kiem_luc > clock_timestamp() - make_interval(secs => :n) "
        "FROM de_cuoi_ky WHERE id = :id"), {"n": HAN_DOC_LAI_GIAY, "id": row.id}))


async def thu_chi_tiet(session: AsyncSession, row: DeCuoiKy, dc: DoiTacClient | None) -> str:
    """Lấy chi tiết sau nộp của bài mức 1 ĐÃ NỘP nếu cần. Gọi khi `row` đã bị khoá (FOR UPDATE).
    Không ném lỗi: kết quả là một trong các hằng ở đầu file, chỗ gọi dựng thông điệp. Chưa commit."""
    if not settings.testbank_chi_tiet_sau_nop_bat:
        return TAT
    if row.dap_an_mo:
        return KHONG_CAN
    if row.het_han_dap_an:
        return HET_HAN
    if dc is None:
        log.warning("Chưa cấu hình dịch vụ phát đề: không lấy được chi tiết sau nộp")
        return LOI_TAM
    if await _vua_hoi(session, row):
        return KHONG_CAN
    try:
        ct = await dc.chi_tiet(row.bai_lam_tb_id)
    except DeliveryLoi as e:
        if e.status == 410:
            row.het_han_dap_an = True
            return HET_HAN
        if e.status == 404:
            if e.ma == MA_KHONG_THAY_BAI:
                # Testbank không còn bài đó: giữ nguyên bản chép + điểm, nhưng người vận hành phải biết.
                log.warning("CANH_BAO testbank_khong_con_bai_lam hs=%s de=%s", row.user_id, row.id)
                row.kiem_luc = func.clock_timestamp()
                return MAT_BAI
            log.warning("CANH_BAO testbank_chua_co_duong_chi_tiet (404 %s) — kiểm tra bản Testbank đã triển "
                        "khai T5 chưa", e.ma or "không mã")
            return KHONG_DUONG
        log.warning("Lấy chi tiết sau nộp lỗi (%s %s)", e.status, e.ma)
        return LOI_TAM
    try:
        async with session.begin_nested():
            await chep_chi_tiet(session, row, ct)
            row.kiem_luc = func.clock_timestamp()
    except Exception:  # noqa: BLE001 — dữ liệu lạ từ Testbank: điểm của em không được mất vì phần phụ
        log.exception("Không chép được chi tiết sau nộp")
        return LOI_TAM
    return OK


# ── Dựng phản hồi ───────────────────────────────────────────────────────────
def giai_doan(row: DeCuoiKy) -> int:
    """0 chưa có chi tiết (hoặc bài mức 0) · 1 chờ thầy cô đóng bài · 2 đã có đáp án."""
    if row.muc != 1 or not row.chi_tiet_json:
        return 0
    return 2 if row.dap_an_mo else 1


def ghi_chu(row: DeCuoiKy, kiem: str | None) -> list[str]:
    """Các dòng trạng thái đặt trên màn kết quả (thông điệp đúng chữ của US-30)."""
    gd = giai_doan(row)
    if gd == 2:
        return [MSG_DA_DONG]
    het = row.het_han_dap_an or kiem == HET_HAN
    if gd == 1:
        if het:
            return [MSG_QUA_HAN]
        dong = [MSG_CHO_DONG]
        if kiem in (LOI_TAM, KHONG_DUONG):
            dong.append(MSG_CHUA_KIEM)
        return dong
    if row.muc != 1:
        return []
    if het:
        return [MSG_QUA_HAN]
    if kiem in (LOI_TAM, KHONG_DUONG):
        return [MSG_DANG_CHUAN_BI]
    return []


def _dung_sai(c: dict) -> dict[str, bool]:
    return ly_do_svc.dung_sai(ly_do_to_de.cau_kieu_kho(c)) if c["phuong_an"] else {}


async def dung_ket_qua(session: AsyncSession, row: DeCuoiKy, tb: TestbankClient | None
                       ) -> tuple[dict, list[tuple[str, dict]]]:
    """`ket_qua` của bài mức 1 ĐÃ NỘP, kèm (khi có bản chép) kết quả theo YCCĐ, khối Đề xuất và — chỉ khi
    `dap_an_mo` — đáp án / lời giải / lý do. Trả thêm việc sinh lý do nền để chỗ gọi lên lịch.

    Khối Đề xuất tính lại mỗi lần theo kho học liệu hiện tại (US-27 Q11), không lưu."""
    kq = json.loads(row.ket_qua_json)
    gd = giai_doan(row)
    if gd == 0:
        return {**kq, "giai_doan": 0}, []
    ct = json.loads(row.chi_tiet_json)["cau"]
    mo = gd == 2
    ban_do = await ck._ban_do_yccd(session, de_xuat_svc.TB_MON, de_xuat_svc.TB_LOP)
    theo_kq = {k["stt"]: k for k in kq["cau"]}
    goc = settings.testbank_content_url

    ly, viec = ({}, [])
    if mo:
        ly, viec = await ly_do_to_de.doc_ly_do(session, tb, ct)

    cau_ra: list[dict] = []
    cho_de_xuat: list[dict] = []
    for c in ct:
        k = theo_kq.get(c["stt"], {})
        # Nhãn / điểm của câu tự luận lấy theo LẦN CHÉP MỚI NHẤT (thầy cô có thể đã chấm); câu chấm
        # tự động giữ đúng như lúc nộp — "đúng / sai, điểm không đổi giữa hai giai đoạn" (KB 14).
        la_tu_luan_da_cham = c["dang"] == "TL" and bool(c.get("trang_thai"))
        trang = c.get("trang_thai") if la_tu_luan_da_cham else (k.get("trang_thai") or c.get("trang_thai"))
        tid, dv = ban_do.get(chuan_hoa(c["ycd"]), (None, ""))
        chon = k.get("chon", "")
        item = {
            "stt": c["stt"], "qid": dl_mod.qid_cau(c["stt"]), "dang": c["dang"], "ar_id": c["ar_id"],
            "ycd": c["ycd"], "muc_do": c["muc_do"], "topic_id": tid, "don_vi": dv, "chon": chon,
            "trang_thai": trang, "nhan": _TRANG_THAI_CHAM.get(trang, k.get("nhan", "Chưa chấm")),
            "diem": c.get("diem") if la_tu_luan_da_cham else k.get("diem", c.get("diem")),
            "diem_toi_da": k.get("diem_toi_da", c.get("diem_toi_da")),
            "cham_duoc": _cham_duoc({**c, "trang_thai": trang}), "dung": trang == "DUNG",
        }
        if mo:
            dap_an = c.get("dap_an") or ""
            kc = cham_svc.cham(c["dang"], dap_an, chon)
            ds = _dung_sai(c)
            li = ly.get(c["stt"], {"ly_do": {}, "trang_thai": "khong"})
            item.update({
                "dap_an": dap_an,
                "dap_an_html": sang_html(dap_an, c["anh"], c["anh_co"], goc=goc),
                "giai_html": sang_html(c.get("bai_giai"), c["anh"], c["anh_co"], goc=goc),
                "so_y_dung": kc.so_y_dung, "so_y": kc.so_y,
                "ly_do": {key: {"noi_dung": nd, "dung": ds.get(key, False)} for key, nd in li["ly_do"].items()},
                "ly_do_ghi_chu": ly_do_to_de.MSG_DANG_CHUAN_BI if li["trang_thai"] == "dang_chuan_bi" else "",
            })
        cau_ra.append(item)
        cho_de_xuat.append({**item, "qid": c["qid"], "dap_an": "", "dap_an_html": None})

    theo_ycd = ck._theo_ycd(cau_ra)
    tu_cham = [x for x in cau_ra if x["cham_duoc"]]
    out = {**kq, "giai_doan": gd, "cau": cho_de_xuat, "theo_ycd": theo_ycd,
           "khong_cham": len(cau_ra) - len(tu_cham)}
    out = await de_xuat_svc.them_de_xuat(
        session, out, loai="testbank", user_id=row.user_id, attempt_id=row.attempt_id, tb=tb,
        bo_hl_theo_cau=True)
    # `qid` thật của kho chỉ dùng để dựng Đề xuất (Test thêm tránh câu đã làm); trình duyệt thấy khoá câu
    # của bài như lúc làm ("c3"). Gộp lại trường chỉ-có-ở-giai-đoạn-2 và cờ `bai_xuat_ban`.
    out["cau"] = [{**it, "bai_xuat_ban": x.get("bai_xuat_ban", False)} for it, x in zip(cau_ra, out["cau"])]
    return out, viec

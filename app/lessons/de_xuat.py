"""Khối "Đề xuất" sau khi nộp bài (US-27): đọc thêm · video · test thêm.

Một chỗ duy nhất quyết định học liệu nào hiện cho học sinh, dùng chung cho cả năm loại
bài làm (Bài kiểm tra nhanh, Ôn tập chương, Luyện thêm, đề cuối kỳ, đề giao) và bài
"Test thêm". Hai bộ gợi ý riêng lẻ trước đây lệch nhau — nhất là ở chỗ "sai phương án
nào" thì không ai biết.

Không gọi LLM, không embed (kho học liệu là dữ liệu cấu trúc do người biên soạn nhập).

Chữ ký công khai (hàm thuần, không DB, không mạng — test thẳng được):
    tinh_de_xuat(cau, hoc_lieu, danh_muc, chua_vung) -> {"loi_khen", "doc_them", "video"}
    chon_ycd_on_lai(lich_su, lan_nay) -> list[ycd_key]          # luật "YCCĐ còn yếu"
    chon_test_them(pool, ar_ids, bo_qid, seed) -> list[qid]     # câu của bài "Test thêm"
    sai_phuong_an(cau) -> set[str]

Phần có I/O: `doc_danh_muc`, `doc_kho_hoc_lieu`, `doc_pool`, `them_de_xuat` (gắn khối
vào kết quả đã chấm), `xoa_cache`.

`de_xuat` KHÔNG BAO GIỜ được lưu trong `ket_qua_json`: học liệu thêm / sửa / xoá thì lần
mở kết quả sau phải thấy bản mới (Q11), và học liệu theo phương án chỉ được trả về
sau khi bài đã chấm (KB 34).
"""
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import security
from app.db.models import (
    BlueprintCell, CurriculumTopic, Grade, HocLieu, QuizAttempt, Subject, TopicContent,
)
from app.integrations.testbank.cham import tach_khoa
from app.integrations.testbank.client import TestbankClient
from app.integrations.testbank.noi_dung import lay_cau
from app.lessons import bo_cuc as bo_cuc_svc
from app.lessons import luyen_them as chon_svc
from app.lessons import ycd_thong_ke as ycd_tk_svc
from app.lessons.ycd_key import chuan_hoa

log = logging.getLogger(__name__)

MON, KHOI = "Toán", "Lớp 6"
#: Mã môn / lớp của testbank cho danh mục trên.
TB_MON, TB_LOP = "TO", "06"

TOI_DA_VIDEO = 3
TOI_DA_BAI_HOC = 5
TOI_DA_HOC_LIEU = 5
#: Bao nhiêu lần nộp gần nhất dùng cho "yếu" / "chưa vững".
GAN_DAY = 5
#: Dưới tỉ lệ này (trên 5 lần nộp gần nhất, >= 2 câu) thì "đúng nhưng chưa vững" (Q6).
NGUONG_VUNG = 0.8
#: Test thêm: 2 câu mỗi YCCĐ, tổng 4-12 (KB 28, hợp đồng §9.9).
CAU_MOI_YCD = 2
TOI_THIEU_TEST_THEM = 4
TOI_DA_TEST_THEM = 12
#: Dựng khối không được kéo dài lúc nộp bài: testbank chậm thì khối suy giảm.
_HAN_TESTBANK_GIAY = 5
#: Cache `ar_id -> nguyên văn YCCĐ` (hợp đồng §4: <= 10 phút).
_TTL_BAN_DO = 10 * 60

MSG_KHONG_HOC_LIEU = "Chưa có học liệu cho phần em làm sai — thử Test thêm để luyện tiếp"
MSG_KHO_CHET = "Chưa tải được video và tài liệu gợi ý, em mở lại sau nhé"
MSG_KHONG_CAU = "Chưa có câu luyện thêm cho phần này"

_NOI_BO = "/video/files/"


# ── Danh mục YCCĐ ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MucYcd:
    """Một YCCĐ trong ma trận, đứng ở bài `topic_id`. `rank` = thứ tự trong ma trận."""
    ycd_key: str
    ycd_text: str
    topic_id: int
    don_vi: str
    xuat_ban: bool
    rank: int


@dataclass
class DanhMuc:
    """Danh mục YCCĐ Toán 6 theo thứ tự ma trận. Một YCCĐ có thể nằm ở nhiều bài (mục
    lục có bài trùng): khi cần chọn bài thì ưu tiên bài chính câu hỏi đang thuộc về,
    nếu không có thì bài đứng trước."""
    muc: list[MucYcd] = field(default_factory=list)
    theo_khoa: dict[str, list[MucYcd]] = field(default_factory=dict)

    @classmethod
    def tu_ds(cls, muc: list[MucYcd]) -> "DanhMuc":
        theo: dict[str, list[MucYcd]] = defaultdict(list)
        for m in muc:
            theo[m.ycd_key].append(m)
        return cls(muc=list(muc), theo_khoa=dict(theo))

    def co(self, ycd_key: str) -> bool:
        return ycd_key in self.theo_khoa

    def tim(self, ycd_key: str, topic_id: int | None = None) -> MucYcd | None:
        ds = self.theo_khoa.get(ycd_key)
        if not ds:
            return None
        if topic_id is not None:
            for m in ds:
                if m.topic_id == topic_id:
                    return m
        return ds[0]

    def duy_nhat(self) -> list[MucYcd]:
        """Mỗi YCCĐ một dòng (dòng đứng trước), theo thứ tự ma trận."""
        thay, ra = set(), []
        for m in self.muc:
            if m.ycd_key not in thay:
                thay.add(m.ycd_key)
                ra.append(m)
        return ra


async def doc_danh_muc(session: AsyncSession) -> DanhMuc:
    rows = (await session.execute(
        select(BlueprintCell.yeu_cau_can_dat, CurriculumTopic.id,
               CurriculumTopic.don_vi_kien_thuc, TopicContent.trang_thai)
        .join(CurriculumTopic, CurriculumTopic.id == BlueprintCell.topic_id)
        .join(Subject, Subject.id == CurriculumTopic.subject_id)
        .join(Grade, Grade.id == CurriculumTopic.grade_id)
        .outerjoin(TopicContent, TopicContent.topic_id == CurriculumTopic.id)
        .where(Subject.name == MON, Grade.name == KHOI)
        .order_by(CurriculumTopic.order_index, CurriculumTopic.id, BlueprintCell.id))).all()
    muc, thay = [], set()
    for ycd, tid, dv, trang_thai in rows:
        khoa = chuan_hoa(ycd)
        if (khoa, tid) in thay:
            continue
        thay.add((khoa, tid))
        muc.append(MucYcd(ycd_key=khoa, ycd_text=(ycd or "").strip(), topic_id=tid,
                          don_vi=(dv or "").strip(), xuat_ban=trang_thai == "published",
                          rank=len(muc)))
    return DanhMuc.tu_ds(muc)


# ── Câu của một bài làm ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class CauKq:
    """Một câu của bài đã chấm, ở dạng mà luật chọn học liệu cần."""
    stt: int
    ycd_key: str
    ycd_text: str
    dung: bool
    cham_duoc: bool = True
    qid: str | None = None
    ar_id: str | None = None
    chon: str = ""
    dap_an: str = ""
    dang: str = "TN1"
    phan: str | None = None
    topic_id: int | None = None


def _y_ds(s: str | None) -> list[str]:
    """Đáp án Đ/S giữ VỊ TRÍ từng ý (ý bỏ trống vẫn chiếm một ô), D = Đ."""
    return ["Đ" if p in ("D", "Đ") else p
            for p in (x.strip().upper() for x in (s or "").replace(";", ",").replace("/", ",").split(","))]


def sai_phuong_an(c: CauKq) -> set[str]:
    """Các phương án em đã chọn SAI trong câu này (giả định 3 của US).

    * Một lựa chọn (TN1): lựa chọn em chọn, nếu câu sai. Bỏ trống thì KHÔNG phải "chọn B".
    * Nhiều lựa chọn (TNN): các lựa chọn em chọn mà không có trong đáp án (chọn thừa).
    * Đúng/sai từng ý (DS): ý nào em trả lời khác đáp án — ý thứ i ứng với khoá chữ cái
      thứ i (A, B, C, D). Ý bỏ trống không tính.
    * Đáp số (DSN) / tự luận: không có phương án."""
    if c.dung or not c.cham_duoc:
        return set()
    if c.dang == "TNN":
        return set(tach_khoa(c.chon)) - set(tach_khoa(c.dap_an))
    if c.dang == "DS":
        dung_, chon_ = _y_ds(c.dap_an), _y_ds(c.chon)
        return {chr(ord("A") + i) for i, d in enumerate(dung_)
                if i < len(chon_) and chon_[i] and chon_[i] != d}
    if c.dang == "TN1":
        return set(tach_khoa(c.chon)[:1])
    return set()


def la_noi_bo(url: str) -> bool:
    return (url or "").startswith(_NOI_BO)


def _muc_hoc_lieu(hl: dict, ghi_chu: str) -> dict:
    url = hl["url"]
    return {"ma": hl["ma"], "loai": hl["loai"], "nhan": hl["nhan"],
            # Video nội bộ phát bằng thẻ <video> (không gửi được header Authorization) nên
            # phải ký URL, như phần minh hoạ trong bài học.
            "url": security.sign_media(url) if la_noi_bo(url) else url,
            "noi_bo": la_noi_bo(url), "muc_dich": hl["muc_dich"], "ghi_chu": ghi_chu}


def _so_cau(ds: list[int]) -> str:
    return ", ".join(str(n) for n in sorted(set(ds)))


def xuat_ban_cua(c: CauKq, danh_muc: DanhMuc) -> bool:
    """Bài học của YCCĐ câu này đã xuất bản chưa; không khớp bài nào -> False (KB 19, 20)."""
    m = danh_muc.tim(c.ycd_key, c.topic_id)
    return bool(m and m.xuat_ban)


# ── Hàm thuần: chọn học liệu ────────────────────────────────────────────────
def tinh_de_xuat(cau: list[CauKq], hoc_lieu: list[dict], danh_muc: DanhMuc,
                 chua_vung: set[str], *, bo_hl_theo_cau: bool = False) -> dict:
    """Chọn học liệu + bài học cho khối Đề xuất (KB 12-25, 27).

    `hoc_lieu`: dict `{ma, loai, nhan, url, muc_dich, ycd_key, qid, option_key}` còn hiệu
    lực. `chua_vung`: các `ycd_key` em làm đúng hết trong bài này nhưng chưa vững theo
    lịch sử. Trả `{"loi_khen", "doc_them", "video"}` (nhóm rỗng -> None).

    Thứ tự trong mỗi nhóm: Ôn lại trước Củng cố; rồi theo phương án -> theo câu -> theo
    YCCĐ; cùng tầng thì thứ tự YCCĐ trong ma trận, thứ tự câu trong đề, mã tăng dần.
    Cùng đầu vào cho ra đúng cùng một danh sách (mở lại kết quả nhiều lần).

    `bo_hl_theo_cau`: bỏ học liệu gắn theo CÂU / PHƯƠNG ÁN (còn lại theo YCCĐ) — bài theo mã Testbank
    (US-30 KB 11): thầy cô có thể đã sửa câu trên tờ đề nên không còn là câu Q của kho."""
    tu_cham = [c for c in cau if c.cham_duoc]
    sai: dict[str, list[CauKq]] = defaultdict(list)
    dung_cua: dict[str, list[CauKq]] = defaultdict(list)
    khong_khop = []
    for c in sorted(tu_cham, key=lambda x: x.stt):
        if not danh_muc.co(c.ycd_key):
            if not c.dung:
                khong_khop.append(c)
            continue
        (dung_cua if c.dung else sai)[c.ycd_key].append(c)
    for c in khong_khop:
        # Không đoán YCCĐ "gần đúng": gắn sai bài mà không ai biết còn tệ hơn không gắn.
        # YCCĐ RỖNG là câu sinh trước khi đề có trường `ycd` (sinh lại đề là hết), không phải chữ lệch.
        (log.error if c.ycd_text else log.warning)(
            "Câu %s (qid=%s) có YCCĐ không khớp danh mục, không đề xuất gì cho câu này: %r",
            c.stt, c.qid, c.ycd_text)

    def rank(khoa: str) -> int:
        return min(m.rank for m in danh_muc.theo_khoa[khoa])

    # ── Học liệu ──
    chon: dict[str, tuple[tuple, dict]] = {}
    for hl in hoc_lieu:
        khoa = hl["ycd_key"]
        if khoa not in danh_muc.theo_khoa:
            continue
        if bo_hl_theo_cau and (hl.get("qid") or hl.get("option_key")):
            continue
        if hl["muc_dich"] == "on_lai":
            ds = sai.get(khoa)
            if not ds:
                continue                    # chỉ YCCĐ CÒN SAI mới có Ôn lại
            if hl.get("qid"):
                c = next((x for x in ds if x.qid == hl["qid"]), None)
                if c is None:
                    continue                # học liệu theo câu chỉ hiện khi sai đúng câu đó
                if hl.get("option_key"):
                    if hl["option_key"].upper() not in sai_phuong_an(c):
                        continue
                    tang, ghi, stt0 = 0, f"Vì em chọn {hl['option_key'].upper()} ở câu {c.stt}", c.stt
                else:
                    tang, ghi, stt0 = 1, f"Liên quan câu {c.stt}", c.stt
            else:
                tang, ghi, stt0 = 2, "Liên quan câu " + _so_cau([x.stt for x in ds]), ds[0].stt
            cung_co = 0
        else:
            # Củng cố: YCCĐ đúng hết nhưng chưa vững. Học liệu Củng cố gắn theo câu chỉ hiện
            # nếu câu đó có trong bài (và em làm đúng).
            if khoa not in chua_vung or khoa in sai:
                continue
            dd = dung_cua.get(khoa) or []
            if hl.get("qid") and hl["qid"] not in {x.qid for x in dd}:
                continue
            tang, ghi, stt0, cung_co = 3, "Củng cố", (dd[0].stt if dd else 0), 1
        khoa_sx = (cung_co, tang, rank(khoa), stt0, hl["ma"])
        if hl["ma"] not in chon or khoa_sx < chon[hl["ma"]][0]:
            chon[hl["ma"]] = (khoa_sx, _muc_hoc_lieu(hl, ghi))
    xep = [m for _k, m in sorted(chon.values(), key=lambda x: x[0])]
    video = [m for m in xep if m["loai"] == "VIDEO"]
    sach = [m for m in xep if m["loai"] != "VIDEO"]

    # ── Bài học cần đọc lại (chỉ bài đã xuất bản) ──
    bai: dict[int, dict] = {}
    for khoa, ds in sai.items():
        for c in ds:
            m = danh_muc.tim(khoa, c.topic_id)
            if m is None or not m.xuat_ban:
                continue
            b = bai.setdefault(m.topic_id, {"topic_id": m.topic_id, "ten": m.don_vi,
                                            "rank": m.rank, "cau": []})
            b["rank"] = min(b["rank"], m.rank)
            b["cau"].append(c)
    bai_hoc = []
    for b in sorted(bai.values(), key=lambda x: (x["rank"], x["topic_id"])):
        cs = sorted(b["cau"], key=lambda x: x.stt)
        # Bố cục chưa chia tới từng ví dụ (hợp đồng §9.1): "phần" là id phần của bài.
        phan = next((c.phan for c in cs if c.phan and c.phan != "kien_thuc"
                     and c.phan in bo_cuc_svc.IDS), "kien_thuc")
        bai_hoc.append({"topic_id": b["topic_id"], "ten": b["ten"], "phan": phan,
                        "ghi_chu": "Sai câu " + _so_cau([c.stt for c in cs])})

    doc_them = ({"bai_hoc": bai_hoc, "hoc_lieu": sach, "toi_da_bai_hoc": TOI_DA_BAI_HOC,
                 "toi_da_hoc_lieu": TOI_DA_HOC_LIEU} if bai_hoc or sach else None)
    loi_khen = (f"Em làm đúng tất cả {len(tu_cham)} câu. Giỏi lắm!"
                if tu_cham and all(c.dung for c in tu_cham) else None)
    return {"loi_khen": loi_khen, "doc_them": doc_them,
            "video": {"hoc_lieu": video, "toi_da": TOI_DA_VIDEO} if video else None}


# ── Hàm thuần: YCCĐ yếu + câu của Test thêm ─────────────────────────────────
def chon_ycd_on_lai(lich_su: list[ycd_tk_svc.ThongKeYcd], lan_nay: list[tuple[str, int, int]],
                    *, toi_da: int = 5) -> list[str]:
    """`ycd_key` của các YCCĐ còn yếu, yếu nhất lên đầu — cùng luật với
    `ycd_thong_ke.chon_ar_on_lai` ("Làm bài mới") nhưng theo khoá YCCĐ, vì câu của Bài
    kiểm tra nhanh chưa có `ar_id`: lịch sử (đủ >= 2 câu, dưới ngưỡng) rồi YCCĐ vừa sai.

    `lan_nay`: (ycd_key, đúng, tổng) của bài vừa nộp."""
    out = [r.ycd_key for r in ycd_tk_svc.con_yeu(lich_su, toi_da=toi_da)]
    sai = sorted((x for x in lan_nay if x[1] < x[2]), key=lambda x: (x[1] / x[2], -x[2], x[0]))
    for khoa, _d, _t in sai:
        if khoa not in out:
            out.append(khoa)
    return out[:toi_da]


def chon_test_them(pool: list[dict], ar_ids: list[str], bo_qid: set[str] | list[str] = (),
                   *, seed: int = 0) -> list[str]:
    """Câu của bài "Test thêm" từ `items` của `/pool` — 2 câu mỗi YCCĐ, tổng 4-12.

    * Tránh `bo_qid` (câu của bài vừa nộp) nếu kho còn câu khác; YCCĐ mà MỌI câu đều đã làm
      thì dùng lại câu cũ, còn hơn bỏ YCCĐ đó (`bo_qid` chỉ là ưu tiên).
    * Chưa đủ 4 câu thì lấy thêm câu của chính các YCCĐ này cho đủ (nếu kho có); không
      đủ thì lấy số đang có.
    * Luật chọn từng câu là của "Luyện thêm" (`luyen_them.chon_cau`): một câu mỗi họ,
      nhóm dữ kiện chung lấy trọn hoặc bỏ.
    Thứ tự: theo thứ tự `ar_ids`, trong mỗi YCCĐ theo thứ tự kho. Cùng đầu vào + cùng
    `seed` -> cùng kết quả."""
    bo = set(bo_qid)
    vi_tri = {x["qid"]: i for i, x in enumerate(pool)}
    da_chon: list[str] = []
    ho_da_dung: set[str] = set()

    def lay(ar: str, so: int, *, cu: bool) -> int:
        ung_vien = [x for x in pool if x.get("ar_id") == ar and x["qid"] not in da_chon
                    and (x["qid"] in bo) == cu and x.get("family_qid") not in ho_da_dung]
        if so <= 0 or not ung_vien:
            return 0
        qs = chon_svc.chon_cau(ung_vien, {ar}, toi_da=so, seed=seed)
        theo = {x["qid"]: x for x in ung_vien}
        for q in qs:
            da_chon.append(q)
            if theo[q].get("family_qid"):
                ho_da_dung.add(theo[q]["family_qid"])
        return len(qs)

    for ar in ar_ids:
        n = lay(ar, CAU_MOI_YCD, cu=False)
        lay(ar, CAU_MOI_YCD - n, cu=True)
    # Chưa đủ 4: thêm mỗi lượt một câu cho từng YCCĐ (câu mới trước, câu cũ sau).
    for cu in (False, True):
        tien = True
        while len(da_chon) < TOI_THIEU_TEST_THEM and tien:
            tien = False
            for ar in ar_ids:
                if len(da_chon) >= TOI_THIEU_TEST_THEM:
                    break
                tien |= lay(ar, 1, cu=cu) > 0
    da_chon = da_chon[:TOI_DA_TEST_THEM] if len(da_chon) > TOI_DA_TEST_THEM else da_chon
    thu_tu_ar = {ar: i for i, ar in enumerate(ar_ids)}
    ar_cua = {x["qid"]: x.get("ar_id") for x in pool}
    return sorted(da_chon, key=lambda q: (thu_tu_ar.get(ar_cua.get(q), 0), vi_tri[q]))


# ── Đọc từ DB / testbank ────────────────────────────────────────────
async def doc_kho_hoc_lieu(session: AsyncSession, ycd_keys: list[str]) -> list[dict]:
    """Học liệu chưa xoá của các YCCĐ này. GỌI QUA MODULE (`de_xuat.doc_kho_hoc_lieu`) để test
    giả lập kho chết được; lỗi bất kỳ thì chỗ gọi chuyển sang nhánh KB 33.

    Truy vấn nằm trong SAVEPOINT: bảng chưa có (API lên trước `./deploy.sh migrate`) hay DB
    trục trặc không được làm hỏng cả giao dịch nộp bài — điểm của em phải được ghi."""
    if not ycd_keys:
        return []
    async with session.begin_nested():
        rows = (await session.scalars(
            select(HocLieu).where(HocLieu.xoa_luc.is_(None), HocLieu.ycd_key.in_(ycd_keys))
            .order_by(HocLieu.ma))).all()
        return [{"ma": r.ma, "loai": r.loai, "nhan": r.nhan, "url": r.url, "muc_dich": r.muc_dich,
                 "ycd_key": r.ycd_key, "qid": r.qid, "option_key": r.option_key} for r in rows]


#: ar_id -> (lúc nạp, nguyên văn YCCĐ). Hợp đồng §4 cho phép cache <= 10 phút.
_BAN_DO_AR: dict[str, tuple[float, str]] = {}
#: `/pool` của Toán 6: (lúc nạp, items). Giữ ngắn (60 giây) để testbank chậm không kéo khối Đề xuất
#: lên tới 5 giây ở MỖI lần mở kết quả, nhưng đủ ngắn để số câu còn lại trong kho gần như luôn mới.
_POOL: tuple[float, list[dict]] | None = None
_TTL_POOL = 60


def xoa_cache() -> None:
    """Xoá cache bản đồ `ar_id <-> YCCĐ` và cache `/pool` (test, hoặc khi vừa nạp lại kho đề)."""
    global _POOL
    _BAN_DO_AR.clear()
    _POOL = None


def _ban_do_ar(items: list[dict]) -> dict[str, str]:
    bay_gio = time.monotonic()
    return {ar: _BAN_DO_AR[ar][1] for ar in {x.get("ar_id") for x in items}
            if ar and ar in _BAN_DO_AR and bay_gio - _BAN_DO_AR[ar][0] < _TTL_BAN_DO}


async def doc_pool(tb: TestbankClient, can_khoa: set[str] | frozenset = frozenset()
                   ) -> tuple[list[dict], dict[str, str]]:
    """`(items của /pool, {ar_id: nguyên văn YCCĐ})` của Toán 6.

    `/pool` chỉ có `ar_id`, không có nguyên văn YCCĐ nên phải resolve — nhưng chỉ MỘT câu đại diện cho
    mỗi ar_id chưa biết, và kết quả được giữ <= 10 phút. `/pool` được giữ 60 giây; nếu cache còn hạn
    mà chưa có YCCĐ nào trong `can_khoa` (khoá YCCĐ đang cần) thì coi như cũ và gọi lại ngay — kho
    vừa đổi thì không phải chờ hết hạn."""
    global _POOL
    bay_gio = time.monotonic()
    items = None
    if _POOL and bay_gio - _POOL[0] < _TTL_POOL:
        da_co = {chuan_hoa(t) for t in _ban_do_ar(_POOL[1]).values()}
        if can_khoa <= da_co:
            items = _POOL[1]
    if items is None:
        pool = await tb.lay("content", "/pool", {"subject": TB_MON, "grade": TB_LOP, "limit": 2000})
        items = pool.get("items") or []
        if pool.get("truncated"):
            log.warning("Pool testbank %s%s bị cắt ở %s câu — Test thêm có thể thiếu câu",
                        TB_MON, TB_LOP, len(items))
        _POOL = (bay_gio, items)
    can_hoi: dict[str, str] = {}
    ban_do = _ban_do_ar(items)
    for x in items:
        ar = x.get("ar_id")
        if ar and ar not in ban_do:
            can_hoi.setdefault(ar, x["qid"])
    if can_hoi:
        for c in await lay_cau(tb, list(can_hoi.values()), include_answers=False):
            if c.get("ar_id"):
                _BAN_DO_AR[c["ar_id"]] = (bay_gio, c.get("yccd_text") or "")
        ban_do = _ban_do_ar(items)
    return items, ban_do


# ── Gắn khối vào kết quả đã chấm ────────────────────────────────────────────
def cau_tu_testbank(ds: list[dict]) -> list[CauKq]:
    """`cau` của kết quả đề cuối kỳ / đề giao / luyện thêm."""
    return [CauKq(stt=int(k.get("stt") or i), ycd_key=chuan_hoa(k.get("ycd") or ""),
                  ycd_text=(k.get("ycd") or "").strip(), dung=bool(k.get("dung")),
                  cham_duoc=bool(k.get("cham_duoc")), qid=k.get("qid") or None,
                  ar_id=k.get("ar_id") or None, chon=k.get("chon") or "",
                  dap_an=k.get("dap_an") or "", dang=k.get("dang") or "TN1",
                  phan=k.get("phan"), topic_id=k.get("topic_id"))
            for i, k in enumerate(ds, start=1)]


def cau_tu_quiz(ds: list[dict], topic_id: int | None = None) -> list[CauKq]:
    """`ket_qua` của Bài kiểm tra nhanh / ôn tập chương: chỉ số phương án -> nhãn chữ."""
    def nhan(i) -> str:
        return chr(ord("A") + i) if isinstance(i, int) and 0 <= i < 26 else ""

    return [CauKq(stt=i, ycd_key=chuan_hoa(k.get("ycd") or ""), ycd_text=(k.get("ycd") or "").strip(),
                  dung=bool(k.get("dung")), chon=nhan(k.get("chon")), dap_an=nhan(k.get("dap_an")),
                  phan=k.get("phan"), topic_id=k.get("topic_id", topic_id))
            for i, k in enumerate(ds, start=1)]


@dataclass
class _TestThem:
    khoi: dict | None
    #: Có YCCĐ yếu nhưng kho đề không có câu nào (chỉ kết luận khi đã hỏi được testbank).
    khong_cau: bool = False


def _noi_ten(ten: list[str]) -> str:
    """Nối tên YCCĐ để đọc: tên kết thúc bằng dấu chấm nên nối thẳng ra ".," — bỏ dấu chấm cuối từng tên."""
    return ", ".join(t.strip().rstrip(".").rstrip() for t in ten)


def _khoi_test_them(yeu: list[str], thong_tin: dict[str, tuple[str, str | None]], bo_qid: list[str],
                    pool: tuple[list[dict], dict[str, str]] | None) -> _TestThem:
    """`thong_tin`: ycd_key -> (tên YCCĐ, ar_id đã biết từ bài làm / lịch sử).
    `pool` None = không hỏi được testbank: trả theo `ar_ids` đã biết, không kiểm độ đủ câu."""
    if not yeu:
        return _TestThem(None)
    if pool is None:
        ar_ids, ten = [], []
        for khoa in yeu:
            t, ar = thong_tin[khoa]
            if ar and ar not in ar_ids:
                ar_ids.append(ar)
                ten.append(t)
        if not ar_ids:
            return _TestThem(None)
        so = min(TOI_DA_TEST_THEM, max(TOI_THIEU_TEST_THEM, CAU_MOI_YCD * len(ar_ids)))
        return _TestThem({"ar_ids": ar_ids, "ycd": ten, "so_cau": so,
                          "mo_ta": f"Bài mới {so} câu về: " + _noi_ten(ten),
                          "thieu": [], "bo_qid": bo_qid})
    items, ar_ycd = pool
    ar_theo_khoa = {}
    for ar, text in ar_ycd.items():
        ar_theo_khoa.setdefault(chuan_hoa(text), ar)
    ung_vien: list[tuple[str, str]] = []                 # (ar_id, tên)
    thieu: list[str] = []
    for khoa in yeu:
        ten, ar = thong_tin[khoa]
        ar = ar or ar_theo_khoa.get(khoa)
        if not ar:
            thieu.append(f"Chưa có câu luyện cho {ten}")
        elif ar not in [a for a, _t in ung_vien]:
            ung_vien.append((ar, ten))
    chon = chon_test_them(items, [a for a, _t in ung_vien], bo_qid)
    ar_cua = {x["qid"]: x.get("ar_id") for x in items}
    co_cau = {ar_cua.get(q) for q in chon}
    ar_ids, ten = [], []
    for ar, t in ung_vien:
        if ar in co_cau:
            ar_ids.append(ar)
            ten.append(t)
        else:
            thieu.append(f"Chưa có câu luyện cho {t}")
    if not ar_ids:
        return _TestThem(None, khong_cau=True)
    return _TestThem({"ar_ids": ar_ids, "ycd": ten, "so_cau": len(chon),
                      "mo_ta": f"Bài mới {len(chon)} câu về: " + _noi_ten(ten),
                      "thieu": thieu, "bo_qid": bo_qid})


def _khoi_rong() -> dict:
    return {"loi_khen": None, "thong_bao": None, "doc_them": None, "video": None, "test_them": None}


async def dung_khoi(session: AsyncSession, cau: list[CauKq], *, user_id: int,
                    attempt_id: int | None, tb: TestbankClient | None,
                    danh_muc: DanhMuc | None = None, hoi_testbank: bool = True,
                    bo_hl_theo_cau: bool = False) -> dict:
    """Dựng `de_xuat` cho một bài đã chấm. Không bao giờ ném lỗi của kho học liệu /
    testbank ra ngoài: điểm và đáp án là việc chính, khối này là phần phụ (KB 33)."""
    danh_muc = danh_muc or await doc_danh_muc(session)
    tu_cham = [c for c in cau if c.cham_duoc]
    khop = [c for c in tu_cham if danh_muc.co(c.ycd_key)]
    khoa_sai = {c.ycd_key for c in khop if not c.dung}
    khoa_dung_het = {c.ycd_key for c in khop} - khoa_sai

    lich_su = await ycd_tk_svc.theo_ycd(session, user_id, gan_day=GAN_DAY, den_attempt_id=attempt_id)
    theo_lich_su = {r.ycd_key: r for r in lich_su}
    chua_vung = {k for k in khoa_dung_het
                 if k in theo_lich_su and theo_lich_su[k].tong >= ycd_tk_svc.TOI_THIEU
                 and theo_lich_su[k].ti_le < NGUONG_VUNG}

    # Kho học liệu: gọi QUA module để test giả lập được; chết thì khối suy giảm.
    kho_loi = False
    hoc_lieu: list[dict] = []
    khoa_can = sorted(khoa_sai | chua_vung)
    try:
        hoc_lieu = await doc_kho_hoc_lieu(session, khoa_can)
    except Exception:  # noqa: BLE001 — kho đọc lỗi: kết quả vẫn phải trọn vẹn
        kho_loi = True
        log.exception("Không đọc được kho học liệu khi dựng khối Đề xuất")

    kq = tinh_de_xuat(cau, hoc_lieu, danh_muc, chua_vung, bo_hl_theo_cau=bo_hl_theo_cau)

    # ── Test thêm ──
    dem: dict[str, list[bool]] = defaultdict(list)
    ten_ar: dict[str, tuple[str, str | None]] = {}
    for c in khop:
        dem[c.ycd_key].append(c.dung)
        t, ar = ten_ar.get(c.ycd_key, (c.ycd_text, None))
        ten_ar[c.ycd_key] = (t, ar or c.ar_id)
    for r in lich_su:
        t, ar = ten_ar.get(r.ycd_key, (r.ycd_text, None))
        ten_ar[r.ycd_key] = (t or r.ycd_text, ar or r.ar_id)
    lan_nay = [(k, sum(v), len(v)) for k, v in dem.items()]
    yeu = [k for k in chon_ycd_on_lai(lich_su, lan_nay) if k in ten_ar]
    bo_qid = list(dict.fromkeys(c.qid for c in cau if c.qid))
    pool = None
    if yeu and tb is not None and hoi_testbank:
        try:
            pool = await asyncio.wait_for(doc_pool(tb, set(yeu)), timeout=_HAN_TESTBANK_GIAY)
        except Exception as e:  # noqa: BLE001 — testbank chết / chậm: trả theo ar_ids đã biết
            log.warning("Không dựng được Test thêm đầy đủ (%s: %s)", type(e).__name__, e)
    tt = _khoi_test_them(yeu, ten_ar, bo_qid, pool)

    # ── Thông báo (chỉ một dòng) ──
    thong_bao = None
    if kho_loi:
        thong_bao = MSG_KHO_CHET
    elif tt.khong_cau:
        thong_bao = MSG_KHONG_CAU
    elif khoa_sai and kq["doc_them"] is None and kq["video"] is None and tt.khoi is not None:
        thong_bao = MSG_KHONG_HOC_LIEU
    return {**kq, "thong_bao": thong_bao, "test_them": tt.khoi}


async def them_de_xuat(session: AsyncSession, ket_qua: dict, *, loai: str, user_id: int,
                       attempt_id: int | None, tb: TestbankClient | None,
                       topic_id: int | None = None, hoi_testbank: bool = True,
                       bo_hl_theo_cau: bool = False) -> dict:
    """BẢN SAO của `ket_qua` kèm `de_xuat` và `bai_xuat_ban` trên từng câu.

    `loai`: "testbank" (kết quả có `cau`: đề cuối kỳ, đề giao, luyện thêm) hoặc "quiz" (kết
    quả có `ket_qua`: Bài kiểm tra nhanh, ôn tập chương). Không sửa `ket_qua` gốc: nó là
    thứ được lưu, còn `de_xuat` phải tính lại theo kho hiện tại mỗi lần trả về.

    Lỗi bất ngờ khi dựng khối -> khối rỗng, kết quả vẫn trả đủ (điểm của em không được mất
    vì một phần phụ), nhưng ghi log đầy đủ để người vận hành thấy.

    `hoi_testbank=False`: không gọi testbank khi dựng khối — "Test thêm" trả theo `ar_ids` đã biết từ
    chính bài làm (không kiểm độ đủ câu). Luyện thêm cần thế: nộp bài luyện thêm KHÔNG gọi kho đề
    (NFR của US-25), và câu của lượt đã nằm trong kho nên các YCCĐ này chắc chắn có câu để "Test thêm"."""
    khoa_ds = "cau" if loai == "testbank" else "ket_qua"
    ds = ket_qua.get(khoa_ds) or []
    cau = cau_tu_testbank(ds) if loai == "testbank" else cau_tu_quiz(ds, topic_id)
    out = {**ket_qua}
    try:
        async with session.begin_nested():
            danh_muc = await doc_danh_muc(session)
            de_xuat = await dung_khoi(session, cau, user_id=user_id, attempt_id=attempt_id,
                                      tb=tb, danh_muc=danh_muc, hoi_testbank=hoi_testbank,
                                      bo_hl_theo_cau=bo_hl_theo_cau)
            xuat_ban = await _xuat_ban_theo_bai(session, cau, loai)
    except Exception:  # noqa: BLE001
        log.exception("Dựng khối Đề xuất lỗi — trả kết quả không kèm đề xuất")
        out["de_xuat"] = _khoi_rong()
        out[khoa_ds] = [{**k, "bai_xuat_ban": False} for k in ds]
        return out
    out["de_xuat"] = de_xuat
    out[khoa_ds] = [{**k, "bai_xuat_ban": xuat_ban_cua(c, danh_muc) if loai == "testbank"
                     else xuat_ban.get(c.topic_id, False)}
                    for k, c in zip(ds, cau)]
    return out


async def _xuat_ban_theo_bai(session: AsyncSession, cau: list[CauKq], loai: str) -> dict[int, bool]:
    """Quiz / ôn tập: bài của từng câu đã biết rõ (không suy từ YCCĐ), nên "Xem lại bài" chỉ
    ẩn khi chính bài đó chưa xuất bản."""
    if loai != "quiz":
        return {}
    ids = {c.topic_id for c in cau if c.topic_id is not None}
    if not ids:
        return {}
    rows = (await session.execute(
        select(TopicContent.topic_id, TopicContent.trang_thai).where(TopicContent.topic_id.in_(ids)))).all()
    return {tid: tt == "published" for tid, tt in rows}

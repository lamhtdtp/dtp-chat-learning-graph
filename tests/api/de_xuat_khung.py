"""Khung dùng chung cho test US-27 (kho học liệu + khối "Đề xuất").

Không phải file test (không có `test_` ở đầu tên) — chỉ có hạ tầng giả và các hàm dựng
dữ liệu, để `test_hoc_lieu_cms.py` và `test_de_xuat.py` cùng dùng.

GIẢ ĐỊNH ĐÃ NÊU (hợp đồng chưa đặt tên / chưa nói rõ — DEV làm theo hoặc báo QC đổi test):
1. Testbank giả cắm qua `app.dependency_overrides[app.api.cuoi_ky.lay_testbank]` cho MỌI đường
   cần testbank, kể cả `/quiz/submit`, `/on-tap/submit`, `/cms/hoc-lieu` (kiểm câu) và
   `/exam/cuoi-ky/test-them`.
2. `de_xuat` nằm ở GỐC phản hồi nộp bài, và nằm TRONG `ket_qua` ở các đường mở lại
   (`GET /exam/cuoi-ky/{id}`, `POST /de-giao/vao`) — hàm `lay_de_xuat` chấp nhận cả hai chỗ.
3. Body CMS gửi `muc_dich` là `"on_lai"` | `"cung_co"` (cùng giá trị với phản hồi).
4. `nguoi_tao` / `nguoi_sua` của danh sách CMS nhận diện được người thao tác qua tên, email
   hoặc id (xem `_la_nguoi`).
"""
import asyncio
import copy
import itertools
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.db.models import (
    Blueprint, BlueprintCell, CurriculumTopic, Grade, QuizAttempt, QuizAttemptItem, Subject,
    TopicContent,
)
from tests.api.conftest import tao_tai_khoan

_OI = itertools.count(90000)          # order_index riêng cho dữ liệu test (sau ma trận thật)
_PA = [{"key": k, "text": t} for k, t in zip("ABCD", ["2", "3", "6", "36"])]
_PA_DS = [{"key": k, "text": f"Khẳng định {k}"} for k in "ABCD"]
DUNG = "C"                              # đáp án đúng của mọi câu TN1 trong khung này
#: dạng -> (đáp án đúng, phương án)
_MAU = {"TN1": (DUNG, _PA), "TNN": ("A,C", _PA), "DS": ("Đ,S,Đ,S", _PA_DS),
        "DSN": ("3,5", []), "TL": ("", [])}


# ── Thế giới dữ liệu: bài + YCCĐ + nội dung ──────────────────────────────────
@dataclass
class Bai:
    tid: int
    ten: str
    ycds: list[str]
    xuat_ban: bool


@dataclass
class TheGioi:
    uid: str
    mach: str
    bai: list[Bai] = field(default_factory=list)

    @property
    def ycds(self) -> list[str]:
        return [y for b in self.bai for y in b.ycds]

    def ar(self, k: int) -> str:
        """Mã YCCĐ bên testbank của YCCĐ thứ k (tăng theo thứ tự ma trận)."""
        return f"AR-{self.uid}-{k}"

    def bai_cua(self, k: int) -> Bai:
        return next(b for b in self.bai if self.ycds[k] in b.ycds)

    def qid(self, i: int) -> str:
        return f"{self.uid}-Q{i}"


async def dung_the_gioi(session, ycd_moi_bai=(2,), xuat_ban=None) -> TheGioi:
    """Dựng Toán 6 → các bài (mỗi bài vài YCCĐ riêng, kèm uuid: DB dev dùng chung).

    `ycd_moi_bai=(1, 1, 1)` -> ba bài, mỗi bài một YCCĐ; thứ tự bài = thứ tự ma trận.
    `xuat_ban` = danh sách bool theo bài (mặc định tất cả đã xuất bản)."""
    subj = await session.scalar(select(Subject).filter_by(name="Toán"))
    grade = await session.scalar(select(Grade).filter_by(name="Lớp 6"))
    if subj is None:
        subj = Subject(name="Toán"); session.add(subj)
    if grade is None:
        grade = Grade(name="Lớp 6"); session.add(grade)
    await session.flush()
    uid = uuid.uuid4().hex[:8]
    the = TheGioi(uid=uid, mach=f"Mạch DX {uid}")
    xuat_ban = list(xuat_ban) if xuat_ban is not None else [True] * len(ycd_moi_bai)
    bp = Blueprint(subject_id=subj.id, grade_id=grade.id, semester=f"dx-{uid}")
    session.add(bp)
    await session.flush()
    k = 0
    for i, so_ycd in enumerate(ycd_moi_bai):
        ten = f"Bài DX {uid} số {i + 1}"
        t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id, mach_noi_dung=the.mach,
                            don_vi_kien_thuc=ten, order_index=next(_OI))
        session.add(t)
        await session.flush()
        ycds = [f"Thực hiện được phép thử {uid} số {k + j}." for j in range(so_ycd)]
        k += so_ycd
        for y in ycds:
            session.add(BlueprintCell(blueprint_id=bp.id, muc_do="de", nang_luc="", topic_id=t.id,
                                      yeu_cau_can_dat=y, dang_thuc="TN", ti_le=1, nhom_ti_le=0))
        session.add(TopicContent(topic_id=t.id, khai_niem=f"<p>Nội dung {ten}</p>",
                                 trang_thai="published" if xuat_ban[i] else "draft"))
        the.bai.append(Bai(tid=t.id, ten=ten, ycds=ycds, xuat_ban=xuat_ban[i]))
    await session.commit()
    return the


# ── Câu hỏi giả ─────────────────────────────────────────────────────────────
@dataclass
class Cau:
    """Một câu của bài làm: thuộc YCCĐ thứ `ycd`, làm đúng hay sai (chọn `chon`)."""
    ycd: int
    dung: bool = True
    chon: str = "A"
    dang: str = "TN1"           # "TL" = tự luận, không chấm tự động (chỉ câu testbank)
    phan: str | None = None     # id phần nội dung gắn với câu (chỉ quiz / ôn tập: vd "vi_du")
    ycd_text: str | None = None # ghi đè nguyên văn YCCĐ của câu (để dựng YCCĐ KHÔNG khớp danh mục)


def cau_tb(the: TheGioi, i: int, c: Cau) -> dict:
    dap_an, phuong_an = _MAU[c.dang]
    return {"qid": the.qid(i), "display_code": f"{the.qid(i)}/{c.dang}", "ar_id": the.ar(c.ycd),
            "yccd_text": c.ycd_text or the.ycds[c.ycd], "difficulty": "B", "format_code": c.dang,
            "competency_code": "GQV", "stem": f"Đề {the.qid(i)} ?", "options": phuong_an,
            "answer_key": dap_an, "explanation": f"Lời giải {the.qid(i)}",
            "family_qid": the.qid(i), "version": "V01", "group_id": None, "stimulus": None,
            "stimulus_lead": None, "assets": {}, "asset_sizes": {}}


def cau_phu(the: TheGioi, k: int, j: int) -> dict:
    """Câu thứ j của kho đề thuộc YCCĐ k, KHÔNG nằm trong bài làm (để "Test thêm" rút)."""
    c = cau_tb(the, 0, Cau(k))
    qid = f"{the.uid}-X{k}{j}"
    return {**c, "qid": qid, "display_code": f"{qid}/TN1", "family_qid": qid}


def tra_loi_cua(c: Cau) -> str:
    if c.dang == "TL":
        return "bài tự luận"
    return _MAU[c.dang][0] if c.dung else c.chon


class TbGia:
    """Thay `TestbankClient`: `lay` (GET /pool) và `goi` (preview + resolve)."""

    __test__ = False

    def __init__(self):
        self.kho: dict[str, dict] = {}
        self.loi: Exception | None = None
        self.treo_giay: float = 0           # >0: mọi lời gọi chờ chừng này giây (testbank không phản hồi)
        self.lay_list: list[tuple] = []
        self.goi_list: list[tuple] = []

    def dat(self, cau_list: list[dict]) -> None:
        self.kho = {c["qid"]: c for c in cau_list}

    def them(self, *cs: dict) -> None:
        for c in cs:
            self.kho[c["qid"]] = c

    async def _truoc(self):
        if self.treo_giay:
            await asyncio.sleep(self.treo_giay)
        if self.loi:
            raise self.loi

    async def lay(self, dich, duong, params):
        self.lay_list.append((dich, duong, params))
        await self._truoc()
        assert (dich, duong) == ("content", "/pool"), duong
        items = [{"qid": c["qid"], "ar_id": c["ar_id"], "difficulty": c["difficulty"],
                  "format_code": c["format_code"], "family_qid": c["family_qid"],
                  "group_id": c["group_id"]} for c in self.kho.values()]
        return {"items": items, "total": len(items), "truncated": False}

    async def goi(self, dich, duong, body):
        self.goi_list.append((dich, duong, body))
        await self._truoc()
        if duong == "/exams:preview":
            ds = [c for c in self.kho.values()
                  if not body.get("ar_ids") or c["ar_id"] in body["ar_ids"]][: body.get("total", 12)]
            return {"quota": {"B": len(ds)}, "is_complete": True, "shortage": {},
                    "pool_size": len(ds), "message": f"Đã rút {len(ds)} câu.",
                    "items": [{"ordinal": i, "qid": c["qid"], "ar_id": c["ar_id"],
                               "difficulty_code": "B", "format_code": c["format_code"]}
                              for i, c in enumerate(ds, start=1)]}
        if duong == "/questions:resolve":
            return [copy.deepcopy(self.kho[q]) for q in body["qids"] if q in self.kho]
        raise AssertionError(duong)


class KhoDemGia:
    """Thay Redis trong `app.llm.cache` (hạn mức + mã đoán sai)."""

    def __init__(self):
        self.d: dict[str, int | str] = {}

    async def incr_quota(self, key, ttl):
        self.d[key] = int(self.d.get(key, 0)) + 1
        return self.d[key]

    async def giam_quota(self, key, ttl):
        self.d[key] = max(int(self.d.get(key, 0)) - 1, 0)

    async def get(self, key):
        return self.d.get(key)

    async def set(self, key, value, ttl=86400):
        self.d[key] = value


# ── Tài khoản ───────────────────────────────────────────────────────────────
async def tk(client, role="hoc_sinh", ten=None) -> SimpleNamespace:
    ten = ten or f"Ten-{uuid.uuid4().hex[:6]}"
    email, h = await tao_tai_khoan(client, role, ten, "dx")
    me = (await client.get("/auth/me", headers=h)).json()
    return SimpleNamespace(h=h, id=me["id"], ten=ten, email=email, role=role)


# ── Học liệu qua CMS ────────────────────────────────────────────────────────
async def them_hl(client, gv, the: TheGioi, ycd: int, *, ma: str | None = None, loai="VIDEO",
                  muc_dich="on_lai", qid: str | None = None, option_key: str | None = None,
                  nhan: str | None = None, url: str | None = None, **kv) -> dict:
    """Thêm một học liệu qua CMS (phải 201). Trả bản học liệu + `ma` đã chuẩn (chữ hoa)."""
    tien_to = {"VIDEO": "VD", "SGK": "SGK", "SBT": "SBT", "BTTC": "BTTC"}[loai]
    ma = ma or f"{tien_to}-{the.uid.upper()}-{uuid.uuid4().hex[:4].upper()}"
    body = {"ma": ma, "loai": loai, "nhan": nhan or f"Nhãn {ma}", "muc_dich": muc_dich,
            "url": url or f"https://hoc-lieu.example.vn/{ma.lower()}", "ycd": the.ycds[ycd], **kv}
    if qid:
        body["qid"] = qid
    if option_key:
        body["option_key"] = option_key
    r = await client.post("/cms/hoc-lieu", headers=gv.h, json=body)
    assert r.status_code == 201, r.text
    return {**r.json(), "ma": ma.upper()}


def lay_de_xuat(resp: dict) -> dict:
    """`de_xuat` ở gốc phản hồi nộp bài, hoặc trong `ket_qua` ở đường mở lại."""
    if "de_xuat" in resp:
        return resp["de_xuat"]
    kq = resp.get("ket_qua")
    if isinstance(kq, dict) and "de_xuat" in kq:
        return kq["de_xuat"]
    raise AssertionError("phản hồi KHÔNG có `de_xuat` (ở gốc hay trong `ket_qua`): "
                         f"khoá có {sorted(resp)}")


def ma_cua(nhom: dict | None) -> list[str]:
    """Các mã học liệu của một nhóm `video` / `doc_them` theo thứ tự hiển thị."""
    return [m["ma"] for m in (nhom or {}).get("hoc_lieu", [])]


def ghi_chu_cua(nhom: dict | None, ma: str) -> str:
    return next(m["ghi_chu"] for m in nhom["hoc_lieu"] if m["ma"] == ma)


# ── Lịch sử làm bài ─────────────────────────────────────────────────────────
async def chen_lich_su(session, user_id: int, lan_nop: list[list[tuple[str, bool]]]) -> None:
    """Chèn các lần nộp CŨ (cuoi_ky) của một học sinh. Mỗi lần: [(ycd_text, đúng?), …].

    `created_at` tăng dần từ năm 2020: `now()` của Postgres là mốc đầu transaction nên mọi
    bản ghi tạo trong test trùng giờ; đặt tay để chắc chắn đây là các lần nộp CŨ hơn lần nộp
    của test."""
    from app.lessons.ycd_key import chuan_hoa

    goc = datetime(2020, 1, 1, 8, 0)
    for i, items in enumerate(lan_nop):
        diem = sum(1 for _y, d in items if d)
        at = QuizAttempt(user_id=user_id, topic_id=None, diem=diem, tong=len(items),
                         dat=False, nguon="cuoi_ky", created_at=goc + timedelta(hours=i))
        session.add(at)
        await session.flush()
        for y, d in items:
            session.add(QuizAttemptItem(attempt_id=at.id, ycd_key=chuan_hoa(y), ycd_text=y,
                                        ar_id=None, qid=None, phan="kien_thuc", muc_do="B",
                                        chon="C" if d else "A", dap_an="C", dung=d))
    await session.commit()


# ── Làm bài theo từng loại ──────────────────────────────────────────────────
LOAI_BAI = ["quiz", "on_tap", "luyen_them", "cuoi_ky", "de_giao", "test_them"]
LOAI_CO_QID = ["luyen_them", "cuoi_ky", "de_giao", "test_them"]
LOAI_KHONG_QID = ["quiz", "on_tap"]


@dataclass
class Ket:
    kq: dict                              # phản hồi của lần nộp
    stt: dict[str, int]                   # qid -> số thứ tự câu trong đề
    mo_lai: object = None                 # async () -> phản hồi mở lại (None nếu loại này không có)
    de_id: str | None = None
    ma_de_giao: str | None = None

    @property
    def de_xuat(self) -> dict:
        return lay_de_xuat(self.kq)


async def dat_quiz(session, the: TheGioi, specs: list[Cau]) -> None:
    """Ghi `quiz_json` của bài đầu cho Bài kiểm tra nhanh / Ôn tập chương
    (`Cau.phan` = phần nội dung gắn với câu, nếu có)."""
    items = []
    for i, c in enumerate(specs, start=1):
        it = {"q": f"Câu {i}?", "o": ["a", "b", "c", "d"], "a": 2, "lv": "de", "giai": "g",
              "ycd": c.ycd_text or the.ycds[c.ycd]}
        if c.phan:
            it["phan"] = c.phan
        items.append(it)
    tc = await session.scalar(select(TopicContent).filter_by(topic_id=the.bai[0].tid))
    tc.quiz_json = json.dumps(items, ensure_ascii=False)
    await session.commit()


def nap_kho(tb: TbGia, the: TheGioi, specs: list[Cau]) -> None:
    """Nạp kho testbank giả bằng đúng các câu của `specs` (câu i -> qid `the.qid(i)`).

    Gọi TRƯỚC khi thêm học liệu gắn theo câu / phương án: CMS kiểm câu qua testbank."""
    tb.dat([cau_tb(the, i, c) for i, c in enumerate(specs, start=1)])


async def lam_bai(loai: str, client, session, tb: TbGia, the: TheGioi, hs, specs: list[Cau],
                  *, ar_test_them: list[int] | None = None, kho_cho_quiz: bool = True,
                  tinh_chinh=None) -> Ket:
    """Làm và nộp một bài thuộc `loai` với kết quả theo `specs` (câu i = specs[i-1]).

    quiz / on_tap: mọi câu thuộc bài đầu của `the` (câu tự sinh, không qid). `tinh_chinh(tb)` chỉ
    áp cho các loại dùng kho testbank cho CHÍNH bài làm; với quiz / on_tap hãy truyền
    `kho_cho_quiz=False` rồi tự `tb.dat(...)`.
    luyen_them: ≤ 4 câu, mọi câu thuộc bài đầu. test_them: ≤ 2 câu mỗi YCCĐ (kho chỉ có đúng các
    câu này nên hệ thống rút trọn chúng)."""
    qs = {the.qid(i): i for i in range(1, len(specs) + 1)}
    if loai in ("quiz", "on_tap"):
        if kho_cho_quiz:
            # Câu quiz do mình tự sinh, không có trong kho đề; kho vẫn có câu CÙNG YCCĐ (qid khác)
            # để "Test thêm" có gì mà rút.
            tb.dat([{**cau_tb(the, i, c), "qid": f"{the.qid(i)}-TB", "family_qid": f"{the.qid(i)}-TB"}
                    for i, c in enumerate(specs, start=1)])
        await dat_quiz(session, the, specs)
        tra = [2 if c.dung else ord(c.chon) - 65 for c in specs]
        if loai == "quiz":
            r = await client.post("/quiz/submit", headers=hs.h,
                                  json={"topic_id": the.bai[0].tid, "answers": tra})
        else:
            r = await client.post("/on-tap/submit", headers=hs.h, json={
                "pham_vi": "mach", "gia_tri": the.mach, "answers": tra})
        assert r.status_code == 200, r.text
        return Ket(kq=r.json(), stt=qs)

    nap_kho(tb, the, specs)
    if tinh_chinh:
        tinh_chinh(tb)                    # vd thêm câu phụ vào kho, đổi YCCĐ của một câu
    tl = {the.qid(i): tra_loi_cua(c) for i, c in enumerate(specs, start=1)}

    if loai == "luyen_them":
        r = await client.post(f"/lessons/{the.bai[0].tid}/luyen-them", headers=hs.h, json={})
        assert r.status_code == 200, r.text
        de = r.json()
        stt = {c["qid"]: c["stt"] for c in de["cau"]}
        r = await client.post("/lessons/luyen-them/submit", headers=hs.h,
                              json={"de_id": de["de_id"], "tra_loi": tl})
        assert r.status_code == 200, r.text
        return Ket(kq=r.json(), stt=stt, de_id=de["de_id"])

    if loai in ("cuoi_ky", "test_them"):
        if loai == "cuoi_ky":
            r = await client.post("/exam/cuoi-ky/generate", headers=hs.h, json={
                "subject": "TO", "grade": "06", "exam": "CK1", "total": len(specs)})
        else:
            ar = [the.ar(k) for k in (ar_test_them or sorted({c.ycd for c in specs}))]
            r = await client.post("/exam/cuoi-ky/test-them", headers=hs.h,
                                  json={"ar_ids": ar, "bo_qid": []})
        assert r.status_code == 200, r.text
        de = r.json()
        stt = {c["qid"]: c["stt"] for c in de["cau"]}
        r = await client.post("/exam/cuoi-ky/submit", headers=hs.h,
                              json={"de_id": de["de_id"], "tra_loi": tl})
        assert r.status_code == 200, r.text

        async def mo_lai():
            x = await client.get(f"/exam/cuoi-ky/{de['de_id']}", headers=hs.h)
            assert x.status_code == 200, x.text
            return x.json()

        return Ket(kq=r.json(), stt=stt, mo_lai=mo_lai, de_id=de["de_id"])

    assert loai == "de_giao", loai
    gv = await tk(client, "giao_vien")
    r = await client.post("/de-giao/xem-truoc", headers=gv.h, json={"exam": "CK1"})
    assert r.status_code == 200, r.text
    r = await client.post(f"/de-giao/{r.json()['nhap_id']}/cap-ma", headers=gv.h)
    assert r.status_code == 200, r.text
    ma = r.json()["ma"]
    r = await client.post("/de-giao/vao", headers=hs.h, json={"ma": ma})
    assert r.status_code == 200, r.text
    de = r.json()
    stt = {c["qid"]: c["stt"] for c in de["cau"]}
    r = await client.post("/de-giao/nop", headers=hs.h, json={"de_id": de["de_id"], "tra_loi": tl})
    assert r.status_code == 200, r.text

    async def mo_lai_giao():
        x = await client.post("/de-giao/vao", headers=hs.h, json={"ma": ma})
        assert x.status_code == 200, x.text
        return x.json()

    return Ket(kq=r.json(), stt=stt, mo_lai=mo_lai_giao, de_id=de["de_id"], ma_de_giao=ma)

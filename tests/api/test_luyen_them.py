"""US-25 — Luyện thêm từ kho đề (rút tối đa 4 câu từ DTP Testbank theo YCCĐ của bài,
chấm ở máy chủ, tính đạt bài khi có >= 3 câu chấm được).

HỢP ĐỒNG (đã chốt với người điều phối; DEV đọc trước khi code)
---------------------------------------------------------------
1. `TestbankClient.lay(dich, duong, params) -> Any` là GET (cùng xử lý token / lỗi như `goi`).
   Testbank giả cắm qua `app.dependency_overrides[app.api.cuoi_ky.lay_testbank]` và có CẢ
   `goi` (POST) lẫn `lay` (GET).
2. Khi rút: `lay("content", "/pool", {"subject": "TO", "grade": "06", "limit": 2000})`
   -> `{"items": [{qid, ar_id, difficulty, format_code, family_qid, group_id}], "total",
   "truncated"}`; rồi `goi("content", "/questions:resolve", {"qids": [...], "include_answers": ..})`
   để biết nguyên văn YCCĐ (`yccd_text`) + nội dung câu. KHÔNG dùng `/exams:preview`. Khớp YCCĐ
   của bài với câu testbank bằng `app.lessons.ycd_key.chuan_hoa` (nguyên văn đã chuẩn hoá, không
   đoán). Tổng mỗi lượt rút <= 2 yêu cầu tới kho (1 lay + 1 goi).
3. `app/lessons/luyen_them.py::chon_cau` (xem tests/lessons/test_luyen_them_chon_cau.py).
4. `POST /lessons/{topic_id}/luyen-them` (body `{}`, cần đăng nhập) -> 200
   `{de_id: str|null, cau: [...], du_cau: bool, thong_bao: str, so_cau_cham_duoc: int, xet_dat: bool}`.
   Mỗi `cau` có ĐÚNG các khoá: stt, qid, dang, muc_do, ar_id, ycd, topic_id, don_vi, de_html,
   phuong_an[{key, html}], du_kien_html, cau_dan, tu_cham — KHÔNG đáp án / lời giải / lý do.
   `xet_dat` = (số câu tự chấm được >= 3). Kho không có câu cho bài / bài không có YCCĐ ->
   200, `de_id: null`, `cau: []`, `thong_bao` khác rỗng (bài không có YCCĐ thì KHÔNG gọi testbank).
   Topic không tồn tại -> 404. Testbank chưa cấu hình / tạm chết -> 503, từ chối (4xx) -> 502;
   `detail` tiếng Việt (đúng chữ trong US). Hạn mức `settings.luyen_them_daily_limit` (mặc định 20):
   quá thì 429 TRƯỚC khi gọi testbank; admin miễn; Redis lỗi thì cho qua. Router ở
   `app/api/luyen_them.py`, đếm bằng `llm_cache.incr_quota` (`from app.llm import cache as llm_cache`).
5. `POST /lessons/luyen-them/submit` body `{"de_id", "tra_loi": {qid: "B"|"A,C"|"Đ,S,Đ,S"|"3,5"}}`
   -> 200: từng câu như đề cuối kỳ (`cau[]`: chon, dung, cham_duoc, dap_an, giai_html,
   ly_do{key:{noi_dung,nguon,dung}}, so_y_dung, so_y, topic_id, don_vi, ycd, ar_id) + `phan`
   ("kien_thuc"); cấp lượt: diem, tong (số câu chấm được), khong_cham, xet_dat, dat_yeu_cau
   (chỉ true khi xet_dat), trang_thai ("dat"|"dang"|"chua", trạng thái bài SAU lượt).
   Đề của người khác / không có -> 404 `Không tìm thấy lượt luyện thêm này.` Nộp lại -> trả đúng
   kết quả lần đầu, không ghi thêm. Nộp KHÔNG gọi testbank, KHÔNG gọi LLM.
6. Ghi: một `QuizAttempt(topic_id=bài, nguon="luyen_them", diem, tong, dat)` + `QuizAttemptItem`
   cho mỗi câu chấm được (ar_id, qid, ycd_key, chon, dap_an, dung). `dat` của attempt = dat_yeu_cau
   (lượt không xét đạt thì False). Xét đạt và >=70% -> `student_progress` thành "dat"; đã "dat"
   không hạ; không xét đạt -> không đổi tiến độ. XP: mỗi câu đúng 5, đạt thêm 10 (như quiz nhanh).
7. `GET /exam/cuoi-ky` KHÔNG liệt kê lượt luyện thêm.
8. CMS `GET /admin/users/{id}/result`: dòng `lan` có `nguon == "luyen_them"`; KHÔNG tính vào
   `tong_lan`, `so_lan_dat`, `diem_tb`, `so_lan`/`tot_nhat`/`gan_nhat` theo đơn vị; có
   `tong_lan_luyen_them` (toàn cục) và `so_lan_luyen_them` (từng đơn vị trong `theo_don_vi`).
9. `GET /me/thoi-gian`: `lich_su[].quiz` có thêm `nguon`.
"Ghi nhận để quản trị tra" (KB5, KB7) = log (logging) mức INFO trở lên chứa tên bài + YCCĐ
(KB5), hoặc ar_id / YCCĐ không khớp (KB7).

Kịch bản KHÔNG viết được ở đây (lý do ở báo cáo): KB1 phần giao diện, KB8 "mở lại lượt" (chưa có
endpoint GET), KB10 thẻ "Hỏi trợ lý" (frontend), KB12 (llm-eval, chỉ contract bên dưới), KB18
nộp đồng thời (fixture dùng một session chung), KB20 "mở" lượt của người khác (chưa có GET).
"""
import json
import logging
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.api import cuoi_ky
from app.config import settings
from app.db.models import (
    Blueprint, BlueprintCell, CurriculumTopic, Grade, QuizAttempt, QuizAttemptItem,
    StudentProgress, Subject, TopicContent, User,
)
from app.integrations.testbank.client import CauHinh, TestbankChuaCauHinh, TestbankLoi
from app.lessons import ycd_thong_ke as ycd_tk_svc
from app.lessons.ycd_key import chuan_hoa
from app.llm.gateway import LLMUnavailable
from app.main import app

ANH = "3f2a" + "0" * 26 + "e9"
_PA = [{"key": k, "text": t} for k, t in zip("ABCD", ["2", "3", "6", "36"])]
_PA_DS = [{"key": k, "text": f"Khẳng định {k}"} for k in "ABCD"]
#: dạng -> (đáp án đúng, phương án, cách trả lời SAI chắc chắn)
_MAU = {
    "TN1": ("B", _PA, "A"), "TNN": ("A,C", _PA, "A"), "DS": ("Đ,S,Đ,S", _PA_DS, "S,Đ,S,Đ"),
    "DSN": ("3,5", [], "99"), "TL": ("Gợi ý bài tự luận", [], "x"),
}
MSG_CHUA_NOI = "Luyện thêm chưa được kết nối với kho câu hỏi. Em làm Bài kiểm tra nhanh ở trên trước nhé!"
MSG_BAN = "Kho đề đang bận, em thử lại sau ít phút nhé."
MSG_SU_CO = "Kho đề đang gặp sự cố, chưa rút được câu. Thầy cô đã được báo."
MSG_KHONG_THAY = "Không tìm thấy lượt luyện thêm này."
KHOA_CAU_CONG_KHAI = {"stt", "qid", "dang", "muc_do", "ar_id", "ycd", "topic_id", "don_vi", "de_html",
                      "phuong_an", "du_kien_html", "cau_dan", "tu_cham"}


# ── Dựng dữ liệu ────────────────────────────────────────────────────────────
async def _bai(session, n_ycd: int = 2) -> SimpleNamespace:
    """Một bài Toán 6 mới + ô ma trận với YCCĐ riêng (kèm uuid: DB dev dùng chung)."""
    subj = await session.scalar(select(Subject).filter_by(name="Toán"))
    grade = await session.scalar(select(Grade).filter_by(name="Lớp 6"))
    if subj is None:
        subj = Subject(name="Toán"); session.add(subj)
    if grade is None:
        grade = Grade(name="Lớp 6"); session.add(grade)
    await session.flush()
    uid = uuid.uuid4().hex[:8]
    ten = f"Bài luyện thêm {uid}"
    t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id, mach_noi_dung="Số tự nhiên",
                        don_vi_kien_thuc=ten, order_index=9999)
    session.add(t); await session.flush()
    ycds = [f"Thực hiện được phép thử {uid} số {i}." for i in range(n_ycd)]
    if n_ycd:
        bp = Blueprint(subject_id=subj.id, grade_id=grade.id, semester=f"lt-{uid}")
        session.add(bp); await session.flush()
        for y in ycds:
            session.add(BlueprintCell(blueprint_id=bp.id, muc_do="de", nang_luc="", topic_id=t.id,
                                      yeu_cau_can_dat=y, dang_thuc="TN", ti_le=1, nhom_ti_le=0))
    tid = t.id            # đọc TRƯỚC commit — sau commit là MissingGreenlet
    await session.commit()
    return SimpleNamespace(tid=tid, ten=ten, ycds=ycds, uid=uid)


def _cau(qid, ar, dang, yccd, *, answer=None, options=None, stem=None, **kv):
    mau = _MAU[dang]
    return {"qid": qid, "display_code": f"{qid}/{dang}", "ar_id": ar, "yccd_text": yccd,
            "difficulty": "B", "format_code": dang, "competency_code": "GQV",
            "stem": stem or f"Đề {qid} ?", "options": mau[1] if options is None else options,
            "answer_key": mau[0] if answer is None else answer,
            "explanation": f"Lời giải gốc {qid}", "family_qid": qid, "version": "V01",
            "group_id": None, "stimulus": None, "stimulus_lead": None,
            "assets": {}, "asset_sizes": {}, **kv}


def _kho(bai, dangs: list[str], ycd_idx: list[int] | None = None) -> list[dict]:
    """Câu thứ i thuộc YCCĐ `ycd_idx[i]` (mặc định luân phiên các YCCĐ của bài)."""
    out = []
    for i, d in enumerate(dangs):
        k = ycd_idx[i] if ycd_idx else i % len(bai.ycds)
        out.append(_cau(f"{bai.uid}-Q{i}", f"AR-{bai.uid}-{k}", d, bai.ycds[k]))
    return out


def _pool_item(c: dict) -> dict:
    return {"qid": c["qid"], "ar_id": c["ar_id"], "difficulty": c["difficulty"],
            "format_code": c["format_code"], "family_qid": c["family_qid"], "group_id": c["group_id"]}


class TestbankGiaLap:
    """Thay `TestbankClient`: `lay` (GET /pool) và `goi` (POST /questions:resolve)."""

    __test__ = False

    def __init__(self, kho: list[dict] | None = None, *, loi: Exception | None = None,
                 loi_o: str = "ca_hai"):
        self.kho = {c["qid"]: c for c in kho or []}
        self.loi, self.loi_o = loi, loi_o
        self.lay_list: list[tuple] = []
        self.goi_list: list[tuple] = []

    @property
    def so_lan_goi(self) -> int:
        return len(self.lay_list) + len(self.goi_list)

    def them(self, *cs: dict) -> None:
        for c in cs:
            self.kho[c["qid"]] = c

    async def lay(self, dich, duong, params):
        self.lay_list.append((dich, duong, params))
        if self.loi and self.loi_o in ("lay", "ca_hai"):
            raise self.loi
        assert (dich, duong) == ("content", "/pool"), duong
        items = [_pool_item(c) for c in self.kho.values()]
        return {"items": items, "total": len(items), "truncated": False}

    async def goi(self, dich, duong, body):
        self.goi_list.append((dich, duong, body))
        if self.loi and self.loi_o in ("goi", "ca_hai"):
            raise self.loi
        assert (dich, duong) == ("content", "/questions:resolve"), duong
        return [self.kho[q] for q in body["qids"] if q in self.kho]


@pytest.fixture
def tb():
    gia = TestbankGiaLap()
    app.dependency_overrides[cuoi_ky.lay_testbank] = lambda: gia
    yield gia
    app.dependency_overrides.pop(cuoi_ky.lay_testbank, None)


@pytest.fixture(autouse=True)
def _llm(mocker):
    """Lý do từng phương án gọi LLM qua `app.exam.ly_do.gateway.complete`. Mặc định trả rỗng."""
    return mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value="{}"))


@pytest.fixture(autouse=True)
def _han_muc(mocker):
    dem = {"n": 0}

    async def incr(key, ttl):
        dem["n"] += 1
        return dem["n"]

    return mocker.patch("app.llm.cache.incr_quota", side_effect=incr)


async def _hs(client, session=None, role="hoc_sinh"):
    email = f"lt-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": role})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    if session is None:
        return h
    uid = await session.scalar(select(User.id).where(User.email == email))
    return h, uid


async def _admin(client, session):
    h, uid = await _hs(client, session)
    u = await session.scalar(select(User).where(User.id == uid))
    u.role = "admin"
    await session.commit()
    return h


async def _rut_tho(client, hs, tid):
    return await client.post(f"/lessons/{tid}/luyen-them", headers=hs, json={})


async def _rut(client, hs, bai):
    r = await _rut_tho(client, hs, bai.tid)
    assert r.status_code == 200, r.text
    return r.json()


async def _nop_tho(client, hs, de_id, tra_loi):
    return await client.post("/lessons/luyen-them/submit", headers=hs,
                             json={"de_id": de_id, "tra_loi": tra_loi})


async def _nop(client, hs, de_id, tra_loi):
    r = await _nop_tho(client, hs, de_id, tra_loi)
    assert r.status_code == 200, r.text
    return r.json()


def _dung(c: dict) -> str:
    return _MAU[c["format_code"]][0] if c["format_code"] != "TL" else "bài tự luận"


def _sai(c: dict) -> str:
    return _MAU[c["format_code"]][2]


def _tra_loi(kho: list[dict], so_dung: int) -> dict[str, str]:
    """`so_dung` câu ĐẦU trả lời đúng, còn lại sai."""
    return {c["qid"]: (_dung(c) if i < so_dung else _sai(c)) for i, c in enumerate(kho)}


async def _lam(client, hs, tb, bai, dangs, so_dung, *, ycd_idx=None):
    kho = _kho(bai, dangs, ycd_idx)
    tb.kho = {c["qid"]: c for c in kho}
    d = await _rut(client, hs, bai)
    kq = await _nop(client, hs, d["de_id"], _tra_loi(kho, so_dung))
    return d, kq


async def _trang_thai(session, uid, tid) -> str:
    v = await session.scalar(select(StudentProgress.trang_thai).filter_by(user_id=uid, topic_id=tid))
    return v or "chua"


async def _datnhom(session, uid, nguon="luyen_them"):
    return (await session.scalars(select(QuizAttempt).where(
        QuizAttempt.user_id == uid, QuizAttempt.nguon == nguon).order_by(QuizAttempt.id))).all()


async def _xp(client, hs) -> int:
    return (await client.get("/me/stats", headers=hs)).json()["xp_total"]


# ═══ A. Hiển thị và rút câu ═════════════════════════════════════════════════
async def test_mo_bai_hoc_khong_goi_kho_va_khong_tao_luot(client, session, tb):
    """KB1: chỉ mở trang bài học thì chưa rút gì, không gọi kho (Q7: tránh tốn kho + LLM)."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    assert (await client.get(f"/lessons/{bai.tid}", headers=hs)).status_code == 200
    assert tb.so_lan_goi == 0
    assert await _datnhom(session, uid) == []


async def test_bai_co_tu_4_cau_tro_len_thi_rut_dung_4_cau_dung_ycd(client, session, tb):
    """KB2: 9 câu đúng YCCĐ của bài + câu của bài khác -> đúng 4 câu, đều thuộc bài này."""
    bai, khac = await _bai(session), await _bai(session)
    kho = _kho(bai, ["TN1", "TNN", "DS", "DSN", "TN1", "TN1", "DSN", "TN1", "TL"])
    kho_khac = [{**c, "qid": "X" + c["qid"]} for c in _kho(khac, ["TN1"] * 3)]
    tb.kho = {c["qid"]: c for c in kho + kho_khac}
    d = await _rut(client, await _hs(client), bai)

    assert d["de_id"] and len(d["cau"]) == 4 and d["du_cau"] is True
    assert [c["stt"] for c in d["cau"]] == [1, 2, 3, 4]
    cua_bai = {c["qid"]: c for c in kho}
    for c in d["cau"]:
        assert c["qid"] in cua_bai                      # không câu bài khác, không câu AI sinh
        assert c["ycd"] in bai.ycds and c["topic_id"] == bai.tid and c["don_vi"] == bai.ten
        assert c["de_html"] and isinstance(c["tu_cham"], bool)
    assert "Kho đề mới có" not in d["thong_bao"]


async def test_rut_goi_testbank_dung_duong_va_toi_da_hai_yeu_cau(client, session, tb):
    """Hợp đồng gọi kho: 1 GET /pool (Toán 6) + 1 POST resolve; không dùng /exams:preview."""
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 6)}
    await _rut(client, await _hs(client), bai)
    assert tb.lay_list[0] == ("content", "/pool", {"subject": "TO", "grade": "06", "limit": 2000})
    assert len(tb.lay_list) == 1 and len(tb.goi_list) == 1
    assert tb.goi_list[0][1] == "/questions:resolve"


async def test_bon_cau_trai_deu_cac_ycd_khong_lap_ho_cau_va_nhom_lien_nhau(client, session, tb):
    """KB3: 3 YCCĐ (mỗi YCCĐ >= 2 câu): mỗi YCCĐ có câu; không hai câu cùng họ; nhóm dữ
    kiện chung đứng liền, dữ kiện hiện một lần; tổng (tính cả câu con) <= 4."""
    hs = await _hs(client)
    bai = await _bai(session, n_ycd=3)
    kho = _kho(bai, ["TN1"] * 6, ycd_idx=[0, 0, 1, 1, 2, 2])
    kho[1]["family_qid"] = kho[0]["family_qid"]          # bản nhân bản của câu 0
    nhom = [_cau(f"{bai.uid}-G{i}", f"AR-{bai.uid}-2", "TN1", bai.ycds[2], group_id=f"{bai.uid}-GR",
                 stimulus="Dữ kiện chung của nhóm", stimulus_lead="Cho biết:") for i in range(2)]
    tb.kho = {c["qid"]: c for c in kho + nhom}
    for _ in range(6):
        d = await _rut(client, hs, bai)
        cau = d["cau"]
        assert len(cau) <= 4
        assert {c["ycd"] for c in cau} == set(bai.ycds)
        ho = [tb.kho[c["qid"]]["family_qid"] for c in cau]
        assert len(ho) == len(set(ho))
        idx = [i for i, c in enumerate(cau) if c["qid"].startswith(f"{bai.uid}-G")]
        if idx:
            assert len(idx) == 2 and idx[1] == idx[0] + 1          # lấy trọn nhóm, liền nhau
            assert cau[idx[0]]["du_kien_html"] and cau[idx[1]]["du_kien_html"] == ""


async def test_kho_it_hon_4_cau_thi_rut_du_va_noi_ro(client, session, tb):
    """KB4: kho chỉ 2 câu đúng YCCĐ -> đúng 2 câu, báo thiếu, báo trước 'chưa đủ 3 câu chấm'."""
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1", "TNN"])}
    d = await _rut(client, await _hs(client), bai)
    assert len(d["cau"]) == 2 and d["du_cau"] is False and d["de_id"]
    assert "Kho đề mới có 2 câu cho bài này." in d["thong_bao"]
    assert ("Lượt này chưa đủ 3 câu chấm tự động nên không tính đạt bài, "
            "em vẫn luyện và xem lời giải được.") in d["thong_bao"]
    assert d["so_cau_cham_duoc"] == 2 and d["xet_dat"] is False


async def test_ba_cau_cham_duoc_thi_xet_dat_va_khong_bao_chua_du_3(client, session, tb):
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1", "TNN", "DS"])}
    d = await _rut(client, await _hs(client), bai)
    assert d["so_cau_cham_duoc"] == 3 and d["xet_dat"] is True
    assert "Kho đề mới có 3 câu cho bài này." in d["thong_bao"]
    assert "chưa đủ 3 câu" not in d["thong_bao"]


async def test_xet_dat_dem_cau_cham_duoc_khong_dem_tong_so_cau(client, session, tb):
    """4 câu nhưng 2 câu tự luận -> chỉ 2 chấm được -> không xét đạt (KB16/17 báo trước ngay khi rút)."""
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1", "TN1", "TL", "TL"])}
    d = await _rut(client, await _hs(client), bai)
    assert len(d["cau"]) == 4 and d["so_cau_cham_duoc"] == 2 and d["xet_dat"] is False
    assert sorted(c["tu_cham"] for c in d["cau"]) == [False, False, True, True]


async def test_bai_khong_co_cau_trong_kho_thi_bao_ro_khong_tao_luot(client, session, tb, caplog):
    """KB5: kho không có câu nào đúng YCCĐ -> de_id null, không nút nộp, không tạo lượt,
    và ghi nhận bài thiếu câu (tên bài + YCCĐ) để quản trị tra."""
    hs, uid = await _hs(client, session)
    bai, khac = await _bai(session), await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(khac, ["TN1"] * 3)}          # chỉ có câu của bài khác
    caplog.set_level(logging.INFO)
    d = await _rut(client, hs, bai)
    assert d["de_id"] is None and d["cau"] == [] and d["so_cau_cham_duoc"] == 0
    assert d["xet_dat"] is False
    assert d["thong_bao"] == "Kho đề chưa có câu hỏi cho bài này. Thầy cô đã được báo."
    assert await _datnhom(session, uid) == [] and await _trang_thai(session, uid, bai.tid) == "chua"
    log = " ".join(r.getMessage() for r in caplog.records)
    assert bai.ten in log and bai.ycds[0] in log


async def test_bai_chua_co_ycd_thi_khong_hoi_kho(client, session, tb):
    """KB6: bài chưa có YCCĐ trong ma trận -> thông báo, KHÔNG gửi yêu cầu nào tới kho."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session, n_ycd=0)
    tb.kho = {c["qid"]: c for c in _kho(await _bai(session), ["TN1"] * 3)}
    d = await _rut(client, hs, bai)
    assert d["de_id"] is None and d["cau"] == []
    assert d["thong_bao"] == "Bài này chưa được gắn yêu cầu cần đạt nên chưa rút được câu luyện thêm."
    assert tb.so_lan_goi == 0
    assert await _datnhom(session, uid) == []


async def test_topic_khong_ton_tai_thi_404(client, tb):
    r = await _rut_tho(client, await _hs(client), 99999999)
    assert r.status_code == 404 and tb.so_lan_goi == 0


async def test_cau_ycd_khong_khop_bi_loai_va_khong_doan_theo_chu(client, session, tb, caplog):
    """KB7: câu có YCCĐ không trùng NGUYÊN VĂN (sau chuẩn hoá) bị loại — kể cả khi chỉ khác dấu
    câu — và được ghi nhận để đối soát."""
    bai = await _bai(session)
    khop = _kho(bai, ["TN1", "TNN", "DS"])
    la = _cau(f"{bai.uid}-LA", f"AR-{bai.uid}-LA", "TN1", f"Một YCCĐ hoàn toàn lạ {bai.uid}.")
    gan_giong = _cau(f"{bai.uid}-GG", f"AR-{bai.uid}-GG", "TN1", bai.ycds[0].rstrip("."))
    tb.kho = {c["qid"]: c for c in khop + [la, gan_giong]}
    caplog.set_level(logging.INFO)
    d = await _rut(client, await _hs(client), bai)
    qids = {c["qid"] for c in d["cau"]}
    assert qids == {c["qid"] for c in khop}
    assert la["qid"] not in qids and gan_giong["qid"] not in qids
    assert "Kho đề mới có 3 câu cho bài này." in d["thong_bao"]
    log = " ".join(r.getMessage() for r in caplog.records)
    assert la["yccd_text"] in log or la["ar_id"] in log


async def test_khop_ycd_chiu_duoc_khac_hoa_thuong_va_khoang_trang(client, session, tb):
    """Chuẩn hoá NFC + gộp khoảng trắng + thường hoá (cùng quy tắc `ycd_key.chuan_hoa`)."""
    bai = await _bai(session, n_ycd=1)
    c = _cau(f"{bai.uid}-K", f"AR-{bai.uid}-0", "TN1", "  " + bai.ycds[0].upper().replace(" ", "  ") + " ")
    assert chuan_hoa(c["yccd_text"]) == chuan_hoa(bai.ycds[0])
    tb.kho = {c["qid"]: c}
    d = await _rut(client, await _hs(client), bai)
    assert [x["qid"] for x in d["cau"]] == [c["qid"]]


async def test_rut_khong_lo_dap_an_loi_giai_ly_do(client, session, tb, _llm):
    """KB8 (bảo mật): trước khi nộp, payload không chứa đáp án, lời giải, lý do từng phương án —
    kiểm cả bằng danh sách khoá cho phép (whitelist) lẫn chuỗi cấm."""
    bai = await _bai(session)
    kho = _kho(bai, ["TN1", "TNN", "DS", "DSN"])
    kho[0]["stem"] = "Đề thuần chữ cho TN1?"
    _llm.return_value = json.dumps({k: f"LY-DO-BI-MAT-{k}" for k in "ABCD"})
    tb.kho = {c["qid"]: c for c in kho}
    d = await _rut(client, await _hs(client), bai)
    for c in d["cau"]:
        assert set(c) == KHOA_CAU_CONG_KHAI, set(c) ^ KHOA_CAU_CONG_KHAI
    raw = json.dumps(d, ensure_ascii=False)
    for cam in ("answer_key", "explanation", "Lời giải", "ly_do", "LY-DO-BI-MAT", "dap_an", "giai",
                "Gợi ý bài tự luận", "3,5", "Đ,S,Đ,S", "A,C"):
        assert cam not in raw, cam
    assert {c["dang"]: c["tu_cham"] for c in d["cau"]} == {"TN1": True, "TNN": True, "DS": True, "DSN": True}


async def test_rut_chi_noi_co_hay_khong_cham_tu_dong(client, session, tb):
    bai = await _bai(session)
    kho = _kho(bai, ["TN1", "TL", "DSN"])
    kho[2]["answer_key"] = f"[[anh:{ANH}]]"
    kho[2]["assets"] = {ANH: "/api/content/media/3f/2a/x.png"}
    tb.kho = {c["qid"]: c for c in kho}
    d = await _rut(client, await _hs(client), bai)
    tc = {c["dang"]: c["tu_cham"] for c in d["cau"]}
    assert tc == {"TN1": True, "TL": False, "DSN": False}


# ═══ B. Nộp bài và chấm (KB9) ═══════════════════════════════════════════════
@pytest.mark.parametrize("dang,dap_an,tra_loi,cham_duoc,dung,y", [
    ("TN1", "B", "B", True, True, None),
    ("TN1", "B", "", True, False, None),
    ("TNN", "A,C", "C, a", True, True, None),
    ("TNN", "A,C", "A", True, False, None),
    ("DS", "Đ,S,Đ,S", "Đ,S,Đ,Đ", True, False, (3, 4)),
    ("DS", "Đ,S,Đ,S", "D,S,D,S", True, True, (4, 4)),
    ("DSN", "3,5", "3.5", True, True, None),
    ("DSN", "3510000", "3.510.000", True, False, None),
    ("DSN", f"[[anh:{ANH}]]", "12", False, False, None),
    ("TL", "Gợi ý", "tuỳ ý", False, False, None),
])
async def test_cham_tung_dang_theo_luat_cua_kho(client, session, tb, dang, dap_an, tra_loi,
                                                cham_duoc, dung, y):
    """KB9: chấm ở máy chủ đúng luật của kho; câu không chấm tự động không có đúng/sai."""
    bai = await _bai(session)
    c = _kho(bai, [dang])[0]
    c["answer_key"] = dap_an
    if ANH in dap_an:
        c["assets"] = {ANH: "/api/content/media/3f/2a/x.png"}
    tb.kho = {c["qid"]: c}
    hs = await _hs(client)
    d = await _rut(client, hs, bai)
    kq = await _nop(client, hs, d["de_id"], {c["qid"]: tra_loi})
    k = kq["cau"][0]
    assert k["cham_duoc"] is cham_duoc and k["dung"] is dung
    if y:
        assert (k["so_y_dung"], k["so_y"]) == y
    assert (kq["diem"], kq["tong"]) == ((1 if dung else 0), (1 if cham_duoc else 0))


async def test_cham_bang_ban_da_luu_khong_tin_trinh_duyet_va_khong_goi_lai_kho(client, session, tb, _llm):
    """KB9 + KB25 + NFR: lúc nộp, kho đổi đáp án rồi chết cũng không ảnh hưởng; trình duyệt gửi kèm
    "đáp án đúng" bị bỏ qua; nộp không gọi kho, không gọi LLM."""
    bai = await _bai(session)
    kho = _kho(bai, ["TN1", "TN1", "TNN"])
    tb.kho = {c["qid"]: c for c in kho}
    hs = await _hs(client)
    d = await _rut(client, hs, bai)
    n_goi, n_llm = tb.so_lan_goi, _llm.await_count

    for c in tb.kho.values():
        c["answer_key"] = "D"                           # kho đổi đáp án sau khi rút
    tb.loi = TestbankLoi("mạng", tam_thoi=True)         # rồi chết hẳn
    r = await client.post("/lessons/luyen-them/submit", headers=hs, json={
        "de_id": d["de_id"], "tra_loi": {c["qid"]: "D" for c in kho},
        "dap_an": {c["qid"]: "D" for c in kho}, "answer_key": "D", "dung": True})
    assert r.status_code == 200, r.text
    kq = r.json()
    assert {k["qid"]: k["dap_an"] for k in kq["cau"]} == {c["qid"]: _MAU[c["format_code"]][0] for c in kho}
    assert kq["diem"] == 0 and kq["tong"] == 3
    assert tb.so_lan_goi == n_goi and _llm.await_count == n_llm


async def test_nop_qid_la_va_thieu_tra_loi_khong_loi(client, session, tb):
    """Người dùng làm bậy: qid không thuộc lượt bị bỏ qua, bỏ trống = sai, không 500."""
    bai = await _bai(session)
    kho = _kho(bai, ["TN1", "TN1", "TN1"])
    tb.kho = {c["qid"]: c for c in kho}
    hs = await _hs(client)
    d = await _rut(client, hs, bai)
    kq = await _nop(client, hs, d["de_id"], {"QID-LA": "A", kho[0]["qid"]: "B"})
    assert (kq["diem"], kq["tong"]) == (1, 3)


async def test_nop_thieu_de_id_thi_422(client, tb):
    r = await client.post("/lessons/luyen-them/submit", headers=await _hs(client), json={"tra_loi": {}})
    assert r.status_code == 422


# ═══ Giải thích sau khi nộp (KB10, KB11) ════════════════════════════════════
async def test_sau_khi_nop_co_chon_dap_an_loi_giai_phan_kien_thuc(client, session, tb):
    """KB10: mỗi câu hiện đã chọn gì, đúng/sai, đáp án, lời giải gốc, 'thuộc phần Kiến thức',
    DS có số ý đúng; cấp lượt có tổng điểm + đã đạt hay chưa."""
    bai = await _bai(session)
    kho = _kho(bai, ["TN1", "DS", "TNN", "DSN"])
    tb.kho = {c["qid"]: c for c in kho}
    hs = await _hs(client)
    d = await _rut(client, hs, bai)
    tl = {kho[0]["qid"]: "B", kho[1]["qid"]: "Đ,S,Đ,Đ", kho[2]["qid"]: "A,C", kho[3]["qid"]: "3,5"}
    kq = await _nop(client, hs, d["de_id"], tl)
    cau = {k["qid"]: k for k in kq["cau"]}
    assert (kq["diem"], kq["tong"], kq["khong_cham"]) == (3, 4, 0)
    assert kq["xet_dat"] is True and kq["dat_yeu_cau"] is True and kq["trang_thai"] == "dat"
    for c in kho:
        k = cau[c["qid"]]
        assert k["chon"] == tl[c["qid"]] and k["dap_an"] == _MAU[c["format_code"]][0]
        assert f"Lời giải gốc {c['qid']}" in k["giai_html"]
        assert k["phan"] == "kien_thuc" and k["topic_id"] == bai.tid and k["don_vi"] == bai.ten
        assert k["ycd"] == c["yccd_text"] and k["ar_id"] == c["ar_id"]
    assert cau[kho[1]["qid"]]["dung"] is False
    assert (cau[kho[1]["qid"]]["so_y_dung"], cau[kho[1]["qid"]]["so_y"]) == (3, 4)


async def test_ly_do_tung_phuong_an_cau_co_hinh_va_ai_loi(client, session, tb, _llm):
    """KB11 (contract, LLM giả): câu 1 thuần chữ có lý do nhãn khớp đáp án kho; câu 3 có hình và
    câu 4 AI lỗi không có lý do nhưng vẫn có đáp án + lời giải; AI lỗi không chặn rút/chấm; nộp
    không gọi LLM; câu có hình không gọi LLM."""
    bai = await _bai(session)
    kho = _kho(bai, ["TN1", "TN1", "TN1", "TN1"])
    kho[0]["stem"], kho[1]["stem"] = "CAU-MOT thuần chữ", "CAU-HAI thuần chữ"
    kho[2]["stem"], kho[2]["assets"] = f"CAU-BA có hình [[anh:{ANH}]]", {ANH: "/api/content/media/3f/2a/x.png"}
    kho[3]["stem"] = "CAU-BON thuần chữ"

    async def gia(task, messages, **kw):
        nd = messages[0]["content"]
        if "CAU-BON" in nd:
            raise LLMUnavailable("403")
        return json.dumps({k: f"Em thấy phương án {k}." for k in "ABCD"})

    _llm.side_effect = gia
    tb.kho = {c["qid"]: c for c in kho}
    hs = await _hs(client)
    d = await _rut(client, hs, bai)                       # LLM lỗi KHÔNG chặn rút
    assert len(d["cau"]) == 4
    prompts = [c.args[1][0]["content"] for c in _llm.await_args_list]
    assert not any("CAU-BA" in p for p in prompts)        # câu có hình: không gọi model
    _llm.reset_mock()
    kq = await _nop(client, hs, d["de_id"], {c["qid"]: "B" for c in kho})
    assert _llm.await_count == 0                          # nộp không chờ LLM
    cau = {k["qid"]: k for k in kq["cau"]}
    ld = cau[kho[0]["qid"]]["ly_do"]
    assert set(ld) == set("ABCD") and ld["B"]["dung"] is True
    assert all(ld[k]["dung"] is False for k in "ACD") and ld["B"]["nguon"] == "ai"
    for i in (2, 3):
        k = cau[kho[i]["qid"]]
        assert k["ly_do"] == {} and k["dap_an"] == "B" and f"Lời giải gốc {kho[i]['qid']}" in k["giai_html"]


async def test_ly_do_dung_lai_cho_luot_sau_khong_goi_llm_lai(client, session, tb, _llm):
    """NFR chi phí: mỗi câu chỉ sinh lý do một lần rồi dùng lại — lượt rút thứ hai 0 lần gọi LLM."""
    bai = await _bai(session)
    kho = _kho(bai, ["TN1", "TN1"])
    _llm.return_value = json.dumps({k: f"Lý do {k}." for k in "ABCD"})
    tb.kho = {c["qid"]: c for c in kho}
    hs = await _hs(client)
    await _rut(client, hs, bai)
    assert _llm.await_count == 2
    _llm.reset_mock()
    d2 = await _rut(client, hs, bai)
    assert _llm.await_count == 0
    kq = await _nop(client, hs, d2["de_id"], {c["qid"]: "B" for c in kho})
    assert all(set(k["ly_do"]) == set("ABCD") for k in kq["cau"])


async def test_toi_da_4_lan_goi_llm_moi_luot_du_kho_co_nhieu_cau(client, session, tb, _llm):
    """NFR chi phí: chỉ sinh lý do cho câu ĐƯỢC CHỌN (<= 4 lần gọi), không cho cả kho đã resolve."""
    bai = await _bai(session)
    kho = _kho(bai, ["TN1"] * 10)
    for c in kho:
        c["stem"] = f"Đề thuần chữ {c['qid']}"
    _llm.return_value = json.dumps({k: f"Lý do {k}." for k in "ABCD"})
    tb.kho = {c["qid"]: c for c in kho}
    d = await _rut(client, await _hs(client), bai)
    assert len(d["cau"]) == 4 and _llm.await_count <= 4


# KB12 [llm-eval]: contract ở trên (KB11 + test dưới). Dataset eval + ngưỡng KHÔNG viết ở lượt này
# (US ghi: dựng eval baseline TRƯỚC khi mở tính năng — việc riêng, cần tài khoản LLM thật).
async def test_prompt_ly_do_neo_dap_an_cua_kho_khong_de_model_tu_quyet(client, session, tb, _llm):
    """KB12 (contract): prompt gửi model ghi sẵn ĐÚNG/SAI theo đáp án của kho và lời giải gốc;
    model không được tự quyết phương án đúng."""
    bai = await _bai(session)
    c = _kho(bai, ["TNN"])[0]                              # đáp án A,C
    c["stem"] = "CAU-TNN thuần chữ"
    tb.kho = {c["qid"]: c}
    await _rut(client, await _hs(client), bai)
    p = _llm.await_args_list[0].args[1][0]["content"]
    dong = {ln[0]: ln for ln in p.splitlines() if ln[:2] in ("A.", "B.", "C.", "D.")}
    assert dong["A"].endswith("ĐÚNG") and dong["C"].endswith("ĐÚNG")
    assert dong["B"].endswith("SAI") and dong["D"].endswith("SAI")
    assert f"Lời giải gốc {c['qid']}" in p


# ═══ C. Luật đạt bài và tiến độ ═════════════════════════════════════════════
@pytest.mark.parametrize("n_cham,n_dung,dat,trang_thai", [
    (4, 4, True, "dat"), (4, 3, True, "dat"), (4, 2, False, "dang"),
    (3, 3, True, "dat"), (3, 2, False, "dang"),
])
async def test_tu_3_cau_cham_duoc_xet_dat_theo_nguong_70(client, session, tb, n_cham, n_dung, dat, trang_thai):
    """KB13: >= 3 câu chấm được thì xét đạt theo 70%; XP: 5/câu đúng + 10 khi đạt; tiến độ đổi."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    xp0 = await _xp(client, hs)
    _, kq = await _lam(client, hs, tb, bai, ["TN1"] * n_cham, n_dung)
    assert (kq["diem"], kq["tong"], kq["xet_dat"]) == (n_dung, n_cham, True)
    assert kq["dat_yeu_cau"] is dat and kq["trang_thai"] == trang_thai
    assert await _trang_thai(session, uid, bai.tid) == trang_thai
    pm = (await client.get("/progress/me", headers=hs)).json()
    dv = next(x for m in pm["mach"] for x in m["dv"] if x["topic_id"] == bai.tid)
    assert dv["trang_thai"] == trang_thai
    at = (await _datnhom(session, uid))[0]
    assert (at.topic_id, at.diem, at.tong, at.dat) == (bai.tid, n_dung, n_cham, dat)
    assert await _xp(client, hs) - xp0 == n_dung * 5 + (10 if dat else 0)


async def _dat_bai_bang_quiz_nhanh(client, session, hs, tid):
    session.add(TopicContent(topic_id=tid, khai_niem="<p>x</p>", trang_thai="published",
                             quiz_json=json.dumps([{"q": f"{i}?", "o": ["a", "b"], "a": 0, "lv": "de"}
                                                   for i in range(5)])))
    await session.commit()
    r = await client.post("/quiz/submit", headers=hs, json={"topic_id": tid, "answers": [0] * 5})
    assert r.status_code == 200 and r.json()["trang_thai"] == "dat"


@pytest.mark.parametrize("cach", ["quiz_nhanh", "luyen_them_truoc", "da_hoan_thanh"])
async def test_da_dat_roi_thi_luyen_them_kem_khong_ha_trang_thai(client, session, tb, cach):
    """KB14: đạt bằng đường nào cũng không bị hạ khi luyện thêm chỉ đúng 1/4."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    if cach == "quiz_nhanh":
        await _dat_bai_bang_quiz_nhanh(client, session, hs, bai.tid)
    elif cach == "luyen_them_truoc":
        _, kq0 = await _lam(client, hs, tb, bai, ["TN1"] * 4, 4)
        assert kq0["trang_thai"] == "dat"
    else:
        r = await client.post("/progress", headers=hs, json={"topic_id": bai.tid, "trang_thai": "dat"})
        assert r.status_code == 200
    _, kq = await _lam(client, hs, tb, bai, ["TN1"] * 4, 1)
    assert kq["diem"] == 1 and kq["tong"] == 4 and kq["dat_yeu_cau"] is False
    assert kq["trang_thai"] == "dat"
    assert await _trang_thai(session, uid, bai.tid) == "dat"
    assert (await _datnhom(session, uid))[-1].dat is False


async def test_dat_bang_luyen_them_van_giu_khi_lam_quiz_nhanh_kem(client, session, tb):
    """KB15."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    await _lam(client, hs, tb, bai, ["TN1"] * 4, 4)
    session.add(TopicContent(topic_id=bai.tid, khai_niem="<p>x</p>", trang_thai="published",
                             quiz_json=json.dumps([{"q": f"{i}?", "o": ["a", "b"], "a": 0, "lv": "de"}
                                                   for i in range(5)])))
    await session.commit()
    r = await client.post("/quiz/submit", headers=hs, json={"topic_id": bai.tid, "answers": [0, 0, 1, 1, 1]})
    assert r.status_code == 200 and r.json()["dat_yeu_cau"] is False       # 40%
    assert r.json()["trang_thai"] == "dat"
    assert await _trang_thai(session, uid, bai.tid) == "dat"


async def test_cau_khong_cham_tu_dong_khong_tinh_diem_va_khong_vao_thong_ke(client, session, tb):
    """KB16: 3 câu chấm được + 1 tự luận: 'Đúng 3/3', xét đạt, bài 'đạt'; TL có gợi ý + lời giải
    nhưng không ghi vào thống kê YCCĐ."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    kho = _kho(bai, ["TN1", "TNN", "DS", "TL"])
    tb.kho = {c["qid"]: c for c in kho}
    d = await _rut(client, hs, bai)
    kq = await _nop(client, hs, d["de_id"], _tra_loi(kho, 4))
    assert (kq["diem"], kq["tong"], kq["khong_cham"]) == (3, 3, 1)
    assert kq["xet_dat"] is True and kq["dat_yeu_cau"] is True and kq["trang_thai"] == "dat"
    tl = next(k for k in kq["cau"] if k["dang"] == "TL")
    assert tl["cham_duoc"] is False and tl["dap_an"] == "Gợi ý bài tự luận"
    assert f"Lời giải gốc {tl['qid']}" in tl["giai_html"]
    qids = set(await session.scalars(select(QuizAttemptItem.qid).join(
        QuizAttempt, QuizAttempt.id == QuizAttemptItem.attempt_id).where(QuizAttempt.user_id == uid)))
    assert qids == {c["qid"] for c in kho if c["format_code"] != "TL"}


@pytest.mark.parametrize("truoc,n_cham,n_khong,n_dung", [
    ("chua", 2, 0, 2), ("chua", 1, 0, 1), ("dang", 2, 1, 2), ("dang", 2, 0, 0), ("chua", 0, 2, 0),
])
async def test_duoi_3_cau_cham_duoc_khong_xet_dat_va_khong_doi_tien_do(
        client, session, tb, truoc, n_cham, n_khong, n_dung):
    """KB17: vẫn chấm, vẫn ghi thống kê, cộng XP theo câu đúng, nhưng không đổi trạng thái bài,
    không thưởng đạt, lượt không phải 'đạt' cũng không phải 'chưa đạt' (xet_dat = false)."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    if truoc == "dang":
        session.add(StudentProgress(user_id=uid, topic_id=bai.tid, trang_thai="dang"))
        await session.commit()
    xp0 = await _xp(client, hs)
    dangs = ["TN1"] * n_cham + ["TL"] * n_khong
    _, kq = await _lam(client, hs, tb, bai, dangs, n_dung)
    assert (kq["diem"], kq["tong"], kq["khong_cham"]) == (n_dung, n_cham, n_khong)
    assert kq["xet_dat"] is False and kq["dat_yeu_cau"] is False and kq["trang_thai"] == truoc
    assert await _trang_thai(session, uid, bai.tid) == truoc
    assert await _xp(client, hs) - xp0 == n_dung * 5
    at = (await _datnhom(session, uid))[0]
    assert (at.diem, at.tong, at.dat) == (n_dung, n_cham, False)
    n_item = await session.scalar(select(func.count()).select_from(QuizAttemptItem)
                                  .where(QuizAttemptItem.attempt_id == at.id))
    assert n_item == n_cham                                       # vẫn ghi thống kê YCCĐ


# ═══ D. Lượt làm bài, đồng thời, quyền ═════════════════════════════════════
async def test_nop_hai_lan_tra_lai_ket_qua_dau_va_khong_ghi_them(client, session, tb):
    """KB18 (tuần tự — nộp đồng thời cần session riêng, xem báo cáo)."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    kho = _kho(bai, ["TN1"] * 4)
    tb.kho = {c["qid"]: c for c in kho}
    d = await _rut(client, hs, bai)
    xp0 = await _xp(client, hs)
    a = await _nop(client, hs, d["de_id"], _tra_loi(kho, 4))
    xp1 = await _xp(client, hs)
    b = await _nop(client, hs, d["de_id"], _tra_loi(kho, 0))      # lần sau bị bỏ qua
    assert a == b and a["diem"] == 4
    assert len(await _datnhom(session, uid)) == 1
    assert await session.scalar(select(func.count()).select_from(QuizAttemptItem).join(
        QuizAttempt, QuizAttempt.id == QuizAttemptItem.attempt_id).where(QuizAttempt.user_id == uid)) == 4
    assert xp1 - xp0 == 4 * 5 + 10 and await _xp(client, hs) == xp1


async def test_lam_lai_la_luot_moi_luot_chua_nop_khong_tinh_vao_dau(client, session, tb):
    """KB19: rút lượt mới = de_id mới; lượt cũ giữ kết quả; lượt rút mà chưa nộp không vào
    tiến độ, thống kê, XP, danh sách lượt trên CMS."""
    hs, uid = await _hs(client, session)
    ad = await _admin(client, session)
    bai = await _bai(session)
    kho = _kho(bai, ["TN1"] * 4)
    tb.kho = {c["qid"]: c for c in kho}
    d1 = await _rut(client, hs, bai)
    k1 = await _nop(client, hs, d1["de_id"], _tra_loi(kho, 4))
    xp1 = await _xp(client, hs)
    d2 = await _rut(client, hs, bai)                              # rút mà chưa nộp
    assert d2["de_id"] and d2["de_id"] != d1["de_id"]
    assert await _nop(client, hs, d1["de_id"], {}) == k1          # lượt cũ không bị ghi đè
    assert len(await _datnhom(session, uid)) == 1
    assert await _xp(client, hs) == xp1
    lan = (await client.get(f"/admin/users/{uid}/result", headers=ad)).json()["lan"]
    assert len([x for x in lan if x["nguon"] == "luyen_them"]) == 1


async def test_khong_nop_duoc_luot_cua_ban_khac_va_thong_bao_giong_luot_khong_ton_tai(client, session, tb):
    """KB20: lượt của A: B nộp nhận 404 cùng thông báo như id không tồn tại; lượt của A không đổi."""
    bai = await _bai(session)
    kho = _kho(bai, ["TN1"] * 4)
    tb.kho = {c["qid"]: c for c in kho}
    a, uid_a = await _hs(client, session)
    d = await _rut(client, a, bai)
    b = await _hs(client)
    r_b = await _nop_tho(client, b, d["de_id"], _tra_loi(kho, 4))
    r_la = await _nop_tho(client, b, "khong-ton-tai-" + uuid.uuid4().hex, {})
    assert r_b.status_code == 404 and r_la.status_code == 404
    assert r_b.json() == r_la.json() == {"detail": MSG_KHONG_THAY}
    assert "Lời giải" not in r_b.text and "dap_an" not in r_b.text
    assert await _datnhom(session, uid_a) == []                   # A chưa nộp, không bị B nộp hộ
    kq = await _nop(client, a, d["de_id"], _tra_loi(kho, 2))
    assert kq["diem"] == 2


@pytest.mark.parametrize("duong", ["rut", "nop"])
async def test_phai_dang_nhap_va_khong_goi_kho(client, tb, duong):
    """KB21."""
    if duong == "rut":
        r = await client.post("/lessons/1/luyen-them", json={})
    else:
        r = await client.post("/lessons/luyen-them/submit", json={"de_id": "x", "tra_loi": {}})
    assert r.status_code in (401, 403) and tb.so_lan_goi == 0


async def test_het_han_muc_ngay_thi_429_truoc_khi_goi_kho(client, session, tb, _han_muc):
    """KB22: quá N lượt/ngày (mặc định 20) -> 429 + thông báo; không gọi kho."""
    assert settings.luyen_them_daily_limit == 20
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}

    async def da_20(key, ttl):
        return 21

    _han_muc.side_effect = da_20
    r = await _rut_tho(client, await _hs(client), bai.tid)
    assert r.status_code == 429
    assert r.json()["detail"] == "Hôm nay em đã luyện thêm 20 lượt rồi, mai làm tiếp nhé!"
    assert tb.so_lan_goi == 0


async def test_han_muc_dung_o_luot_thu_20_va_chan_o_luot_21(client, session, tb, _han_muc):
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    hs = await _hs(client)
    for _ in range(20):
        assert (await _rut_tho(client, hs, bai.tid)).status_code == 200
    assert (await _rut_tho(client, hs, bai.tid)).status_code == 429


async def test_admin_khong_bi_gioi_han_han_muc(client, session, tb, _han_muc):
    async def da_vuot(key, ttl):
        return 999

    _han_muc.side_effect = da_vuot
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    assert (await _rut_tho(client, await _admin(client, session), bai.tid)).status_code == 200


async def test_bo_dem_loi_thi_van_cho_rut(client, session, tb, _han_muc):
    """KB22: Redis lỗi -> fail-open, không chặn học sinh."""
    _han_muc.side_effect = ConnectionError("redis chết")
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    assert (await _rut_tho(client, await _hs(client), bai.tid)).status_code == 200


async def test_han_muc_luyen_them_rieng_voi_de_cuoi_ky(client, session, tb, _han_muc):
    """Q6: hạn mức riêng — khoá đếm của luyện thêm không trùng khoá của đề cuối kỳ."""
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    await _rut(client, await _hs(client), bai)
    khoa = [c.args[0] if c.args else c.kwargs["key"] for c in _han_muc.call_args_list]
    assert khoa and not any(k.startswith("dequota:") for k in khoa)


# ═══ E. Kho đề lỗi ══════════════════════════════════════════════════════════
async def test_kho_chua_cau_hinh_thi_503_va_thong_bao_dung_chu(client, session, mocker, _han_muc):
    """KB23: chưa cấu hình -> 503 + thông điệp tiếng Việt của mục luyện thêm (KHÔNG phải câu của
    đề cuối kỳ); không trừ hạn mức; phần còn lại của bài học vẫn dùng được."""
    mocker.patch.object(CauHinh, "tu_settings",
                        side_effect=TestbankChuaCauHinh(["TESTBANK_EMAIL"]))
    hs = await _hs(client)
    bai = await _bai(session)
    r = await _rut_tho(client, hs, bai.tid)
    assert r.status_code == 503 and r.json()["detail"] == MSG_CHUA_NOI
    assert _han_muc.call_count == 0
    assert (await client.get(f"/lessons/{bai.tid}", headers=hs)).status_code == 200


@pytest.mark.parametrize("o", ["lay", "goi"])
@pytest.mark.parametrize("loi,ma,msg", [
    (TestbankLoi("mạng", tam_thoi=True), 503, MSG_BAN),
    (TestbankLoi("5xx", tam_thoi=True, ma=500), 503, MSG_BAN),
    (TestbankLoi("403", tam_thoi=False, ma=403), 502, MSG_SU_CO),
    (TestbankLoi("401", tam_thoi=False, ma=401), 502, MSG_SU_CO),
])
async def test_loi_kho_khi_rut_thanh_thong_bao_tieng_viet_khong_tao_luot(
        client, session, tb, caplog, loi, ma, msg, o):
    """KB24: lỗi tạm thời -> 503, kho từ chối -> 502 (giám sát phân biệt được); lỗi ở bước
    lấy danh sách (GET) hay lấy nội dung (POST) đều như nhau; không tạo lượt."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    tb.kho = {c["qid"]: c for c in _kho(bai, ["TN1"] * 4)}
    tb.loi, tb.loi_o = loi, o
    r = await _rut_tho(client, hs, bai.tid)
    assert r.status_code == ma and r.json()["detail"] == msg
    assert "Kho đề" in r.json()["detail"]
    assert await _datnhom(session, uid) == []
    assert (await client.get("/exam/cuoi-ky", headers=hs)).json()["de"] == []
    assert (await client.get(f"/lessons/{bai.tid}", headers=hs)).status_code == 200


async def test_kho_chet_sau_khi_rut_van_nop_va_cham_duoc(client, session, tb):
    """KB25: kho chết sau khi rút -> nộp vẫn chấm, tiến độ + XP + thống kê YCCĐ cập nhật."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    kho = _kho(bai, ["TN1"] * 4)
    tb.kho = {c["qid"]: c for c in kho}
    d = await _rut(client, hs, bai)
    tb.loi = TestbankLoi("kho chết", tam_thoi=True)
    xp0 = await _xp(client, hs)
    kq = await _nop(client, hs, d["de_id"], _tra_loi(kho, 4))
    assert kq["diem"] == 4 and kq["trang_thai"] == "dat"
    assert await _trang_thai(session, uid, bai.tid) == "dat"
    assert await _xp(client, hs) - xp0 == 30
    assert sum(r.tong for r in await ycd_tk_svc.theo_ycd(session, uid)) == 4


# ═══ F. Thống kê, hồ sơ, CMS ═══════════════════════════════════════════════
async def test_ket_qua_vao_thong_ke_theo_ycd_va_goi_y(client, session, tb):
    """KB26: 2 câu chấm được thuộc cùng YCCĐ, đúng 1 -> YCCĐ hiện 1/2; câu tự luận không ghi;
    cùng nguồn tính với quiz nhanh / đề cuối kỳ (`ycd_thong_ke.theo_ycd`)."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session, n_ycd=1)
    kho = _kho(bai, ["TN1", "TN1", "TL"])
    tb.kho = {c["qid"]: c for c in kho}
    d = await _rut(client, hs, bai)
    await _nop(client, hs, d["de_id"], _tra_loi(kho, 1))
    ycd = (await client.get("/me/ycd", headers=hs)).json()
    cell = next(y for m in ycd["mach"] for y in m["ycd"] if y["ycd"] == bai.ycds[0])
    assert (cell["dung"], cell["tong"], cell["sai"]) == (1, 2, 1)
    tk = {r.ycd_key: r for r in await ycd_tk_svc.theo_ycd(session, uid)}
    r = tk[chuan_hoa(bai.ycds[0])]
    assert (r.dung, r.tong) == (1, 2)
    it = (await session.scalars(select(QuizAttemptItem).join(
        QuizAttempt, QuizAttempt.id == QuizAttemptItem.attempt_id)
        .where(QuizAttempt.user_id == uid).order_by(QuizAttemptItem.id))).all()
    assert [(i.qid, i.ar_id, i.ycd_key, i.chon, i.dap_an, i.dung) for i in it] == [
        (kho[0]["qid"], kho[0]["ar_id"], chuan_hoa(bai.ycds[0]), "B", "B", True),
        (kho[1]["qid"], kho[1]["ar_id"], chuan_hoa(bai.ycds[0]), "A", "B", False)]


async def test_ho_so_hien_luot_luyen_them_co_nhan_nguon(client, session, tb):
    """KB27: /me/thoi-gian có `quiz.nguon == "luyen_them"` cho phiên của bài; số bài đạt khớp."""
    from datetime import timedelta

    from app.db.models import StudySession

    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    await _lam(client, hs, tb, bai, ["TN1"] * 4, 3)
    luc = await session.scalar(select(QuizAttempt.created_at).where(QuizAttempt.user_id == uid))
    session.add(StudySession(user_id=uid, topic_id=bai.tid, mo_luc=luc - timedelta(minutes=10),
                             dong_luc=luc - timedelta(minutes=1), so_giay=540, phan_doc_json="[]"))
    await session.commit()
    ls = (await client.get("/me/thoi-gian", headers=hs)).json()["lich_su"]
    q = next(x for x in ls if x["topic_id"] == bai.tid)["quiz"]
    assert (q["diem"], q["tong"], q["dat"], q["nguon"]) == (3, 4, True, "luyen_them")
    pm = (await client.get("/progress/me", headers=hs)).json()
    assert next(x for m in pm["mach"] for x in m["dv"] if x["topic_id"] == bai.tid)["trang_thai"] == "dat"


async def test_cms_tach_luot_luyen_them_khoi_quiz_nhanh(client, session, tb):
    """KB28: 2 lần quiz nhanh (50%, 60%) + 1 lượt luyện thêm 75% đạt -> 3 dòng, dòng luyện thêm có
    nhãn; bài 'đạt'; so_lan_luyen_them = 1; số lần / đạt / điểm TB / tốt nhất / gần nhất của quiz
    nhanh chỉ tính 2 lần; tổng lượt luyện thêm hiện riêng."""
    hs, uid = await _hs(client, session)
    ad = await _admin(client, session)
    bai = await _bai(session)
    session.add_all([
        QuizAttempt(user_id=uid, topic_id=bai.tid, diem=1, tong=2, dat=False, nguon="nhanh",
                    created_at=datetime(2000, 1, 1)),
        QuizAttempt(user_id=uid, topic_id=bai.tid, diem=3, tong=5, dat=False, nguon="nhanh",
                    created_at=datetime(2000, 1, 2)),
    ])
    await session.commit()
    await _lam(client, hs, tb, bai, ["TN1"] * 4, 3)

    b = (await client.get(f"/admin/users/{uid}/result", headers=ad)).json()
    nguon = sorted(x["nguon"] for x in b["lan"])
    assert nguon == ["luyen_them", "nhanh", "nhanh"]
    lt = next(x for x in b["lan"] if x["nguon"] == "luyen_them")
    assert lt["phan_tram"] == 75 and lt["dat"] is True
    assert b["tong_lan"] == 2 and b["so_lan_dat"] == 0 and b["diem_tb"] == 55
    assert b["tong_lan_luyen_them"] == 1
    assert b["tong_lan_on_tap"] == 0 and b["tong_lan_cuoi_ky"] == 0
    dv = next(g for g in b["theo_don_vi"] if g["topic_id"] == bai.tid)
    assert dv["trang_thai"] == "dat" and dv["so_lan_luyen_them"] == 1
    assert dv["so_lan"] == 2 and dv["tot_nhat"] == 60 and dv["gan_nhat"] == 60


async def test_cms_chi_co_luot_luyen_them_thi_khong_tao_so_lieu_quiz_nhanh(client, session, tb):
    """Bài chỉ có luyện thêm: so_lan = 0, tot_nhat/gan_nhat = None (không phải 0%), diem_tb không bị kéo."""
    hs, uid = await _hs(client, session)
    ad = await _admin(client, session)
    bai = await _bai(session)
    await _lam(client, hs, tb, bai, ["TN1"] * 4, 4)
    b = (await client.get(f"/admin/users/{uid}/result", headers=ad)).json()
    assert b["tong_lan"] == 0 and b["so_lan_dat"] == 0 and b["tong_lan_luyen_them"] == 1
    dv = next(g for g in b["theo_don_vi"] if g["topic_id"] == bai.tid)
    assert (dv["so_lan"], dv["tot_nhat"], dv["gan_nhat"], dv["so_lan_luyen_them"]) == (0, None, None, 1)
    assert dv["trang_thai"] == "dat"


async def test_lich_su_de_cuoi_ky_khong_liet_ke_luot_luyen_them(client, session, tb):
    """Hợp đồng 7: GET /exam/cuoi-ky không có lượt luyện thêm — cả đã nộp lẫn mới rút."""
    hs, _ = await _hs(client, session)
    bai = await _bai(session)
    await _lam(client, hs, tb, bai, ["TN1"] * 4, 4)                # đã nộp
    await _rut(client, hs, bai)                                    # mới rút
    r = (await client.get("/exam/cuoi-ky", headers=hs)).json()
    assert r["de"] == []


async def test_xoa_lich_su_de_cuoi_ky_khong_dong_den_luot_luyen_them(client, session, tb):
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    await _lam(client, hs, tb, bai, ["TN1"] * 4, 4)
    assert (await client.delete("/exam/cuoi-ky", headers=hs)).json()["da_xoa"] == 0
    assert len(await _datnhom(session, uid)) == 1


def test_setting_han_muc_mac_dinh_20():
    assert settings.luyen_them_daily_limit == 20

"""Lý do từng phương án (nhánh C1). Chạm LLM nên chỉ test HỢP ĐỒNG — mock ở
ranh giới gateway, đúng đường import `app.exam.ly_do.gateway.complete`. Chất
lượng lời giải thích là việc của eval, không phải ở đây."""
import json
import uuid

from sqlalchemy import select

from app.db.models import LyDoPhuongAn
from app.exam import ly_do
from app.llm.gateway import LLMUnavailable

ANH = "[[anh:" + "a" * 32 + "]]"


def _cau(**kv) -> dict:
    c = {"qid": f"Q-{uuid.uuid4().hex[:8]}", "version": "V01", "format_code": "TN1",
         "stem": "ƯCLN(12; 18) bằng?",
         "options": [{"key": "A", "text": "2"}, {"key": "B", "text": "3"},
                     {"key": "C", "text": "6"}, {"key": "D", "text": "36"}],
         "answer_key": "C", "explanation": "12 = 2²·3, 18 = 2·3² nên ƯCLN = 6."}
    c.update(kv)
    return c


# ── đúng/sai theo phương án ─────────────────────────────────────────────────
def test_dung_sai_tn1():
    assert ly_do.dung_sai(_cau()) == {"A": False, "B": False, "C": True, "D": False}


def test_dung_sai_tnn():
    assert ly_do.dung_sai(_cau(format_code="TNN", answer_key="A,C"))["A"] is True


def test_dung_sai_ds_theo_vi_tri_y():
    c = _cau(format_code="DS", answer_key="Đ,S,D,S")
    assert ly_do.dung_sai(c) == {"A": True, "B": False, "C": True, "D": False}


# ── có nên sinh không ────────────────────────────────────────────────────────
def test_sinh_cho_cau_trac_nghiem_chu():
    assert ly_do.can_sinh(_cau())


def test_khong_sinh_khi_de_hoac_phuong_an_co_hinh():
    """Model chỉ thấy "[hình]" — viết lý do cho phương án mình không nhìn thấy
    là bịa. Thà không có dòng lý do còn hơn một dòng sai."""
    assert not ly_do.can_sinh(_cau(stem=f"Tổng {ANH} bằng?"))
    opts = _cau()["options"]
    opts[1] = {"key": "B", "text": ANH}
    assert not ly_do.can_sinh(_cau(options=opts))


def test_khong_sinh_cho_dang_khong_co_phuong_an():
    assert not ly_do.can_sinh(_cau(format_code="DSN", options=[], answer_key="21"))
    assert not ly_do.can_sinh(_cau(format_code="TL"))


def test_khong_sinh_khi_thieu_dap_an():
    assert not ly_do.can_sinh(_cau(answer_key=""))


# ── prompt + bóc kết quả ─────────────────────────────────────────────────────
def test_prompt_noi_ro_phuong_an_nao_dung_va_kem_loi_giai_goc():
    """Model không được tự quyết đáp án — mình nói trước, nó chỉ diễn giải."""
    p = ly_do.tao_prompt(_cau())
    assert "C. 6 — ĐÚNG" in p and "D. 36 — SAI" in p
    assert "ƯCLN = 6" in p


def test_boc_bo_khoa_la_va_dong_rong():
    raw = json.dumps({"A": "2 chỉ là ước chung.", "B": "", "C": "Đúng vì…", "Z": "bịa"})
    assert ly_do.boc_ly_do(raw, ["A", "B", "C", "D"]) == {"A": "2 chỉ là ước chung.",
                                                         "C": "Đúng vì…"}


def test_boc_rac_ra_rong_khong_no():
    assert ly_do.boc_ly_do("xin lỗi, tôi không biết", ["A"]) == {}


# ── đảm bảo có lý do (cache theo qid + version) ──────────────────────────────
def _tra(**kv):
    return json.dumps({"A": "a", "B": "b", "C": "c", "D": "d", **kv})


async def test_sinh_roi_luu_theo_qid_version(db_session, mocker):
    llm = mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value=_tra()))
    c = _cau()
    out = await ly_do.dam_bao_ly_do(db_session, [c])
    assert out[c["qid"]]["C"] == {"noi_dung": "c", "nguon": "ai"}
    assert llm.await_args.args[0] == "rationale_gen"
    rows = (await db_session.scalars(select(LyDoPhuongAn).filter_by(qid=c["qid"]))).all()
    assert {(r.version, r.option_key) for r in rows} == {("V01", k) for k in "ABCD"}


async def test_lan_sau_doc_cache_khong_goi_model(db_session, mocker):
    c = _cau()
    mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value=_tra()))
    await ly_do.dam_bao_ly_do(db_session, [c])
    llm = mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value=_tra()))
    out = await ly_do.dam_bao_ly_do(db_session, [c])
    assert llm.await_count == 0 and out[c["qid"]]["A"]["noi_dung"] == "a"


async def test_version_moi_thi_sinh_lai(db_session, mocker):
    """Câu được sửa -> lý do cũ có thể sai với nội dung mới."""
    c = _cau()
    mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value=_tra()))
    await ly_do.dam_bao_ly_do(db_session, [c])
    llm = mocker.patch("app.exam.ly_do.gateway.complete",
                       mocker.AsyncMock(return_value=_tra(A="mới")))
    out = await ly_do.dam_bao_ly_do(db_session, [{**c, "version": "V02"}])
    assert llm.await_count == 1 and out[c["qid"]]["A"]["noi_dung"] == "mới"


async def test_nguon_testbank_uu_tien_hon_ai(db_session, mocker):
    """C2: khi testbank có `rationale` chính thức thì dùng bản đó, AI chỉ lấp chỗ trống."""
    c = _cau()
    db_session.add(LyDoPhuongAn(qid=c["qid"], version="V01", option_key="D",
                                noi_dung="36 là BCNN, không phải ƯCLN.", nguon="testbank"))
    await db_session.flush()
    mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value=_tra()))
    out = await ly_do.dam_bao_ly_do(db_session, [c])
    assert out[c["qid"]]["D"] == {"noi_dung": "36 là BCNN, không phải ƯCLN.", "nguon": "testbank"}
    assert out[c["qid"]]["A"]["nguon"] == "ai"


async def test_model_het_quota_thi_bo_qua_khong_lam_hong_de(db_session, mocker):
    """Lý do là phần PHỤ: model chết thì đề vẫn phải ra, chỉ thiếu dòng lý do."""
    mocker.patch("app.exam.ly_do.gateway.complete",
                 mocker.AsyncMock(side_effect=LLMUnavailable("429")))
    c = _cau()
    assert await ly_do.dam_bao_ly_do(db_session, [c]) == {}


async def test_khong_goi_model_cho_cau_khong_sinh_duoc(db_session, mocker):
    llm = mocker.patch("app.exam.ly_do.gateway.complete", mocker.AsyncMock(return_value=_tra()))
    await ly_do.dam_bao_ly_do(db_session, [_cau(stem=f"Tổng {ANH}?"),
                                           _cau(format_code="DSN", options=[], answer_key="2")])
    assert llm.await_count == 0

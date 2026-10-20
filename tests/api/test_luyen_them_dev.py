"""US-25 — test bổ sung của DEV (ngoài bộ RED của QC): luật `truot_bai` ở /me/ycd,
`TestbankClient.lay` (GET), nhãn `nguon` ở hồ sơ."""
import uuid

import httpx
from sqlalchemy import select

from app.db.models import QuizAttempt
from app.integrations.testbank.client import CauHinh, KhoTokenBoNho, TestbankClient, TestbankLoi
from tests.api.test_luyen_them import _bai, _hs  # noqa: F401  (dựng bài + học sinh)


async def _truot_bai(client, hs, tid) -> int:
    ycd = (await client.get("/me/ycd", headers=hs)).json()
    return next(y["truot_bai"] for m in ycd["mach"] for y in m["ycd"] if y["topic_id"] == tid)


async def test_truot_bai_khong_dem_luot_luyen_them_khong_xet_dat(client, session):
    """Quyết định US-25 #3: lượt luyện thêm dưới 3 câu chấm được (dat=False nhưng KHÔNG phải
    trượt) không được đếm vào `truot_bai`; lượt xét đạt mà trượt thì đếm như trượt bài."""
    hs, uid = await _hs(client, session)
    bai = await _bai(session)
    session.add_all([
        QuizAttempt(user_id=uid, topic_id=bai.tid, diem=1, tong=2, dat=False, nguon="luyen_them"),
        QuizAttempt(user_id=uid, topic_id=bai.tid, diem=0, tong=1, dat=False, nguon="luyen_them"),
    ])
    await session.commit()
    assert await _truot_bai(client, hs, bai.tid) == 0

    session.add_all([
        QuizAttempt(user_id=uid, topic_id=bai.tid, diem=1, tong=4, dat=False, nguon="luyen_them"),
        QuizAttempt(user_id=uid, topic_id=bai.tid, diem=1, tong=4, dat=False, nguon="nhanh"),
    ])
    await session.commit()
    assert await _truot_bai(client, hs, bai.tid) == 2


async def test_testbank_client_lay_la_get_co_token_va_params():
    """`lay` = GET, cùng token Bearer + cùng cách đổi lỗi như `goi`."""
    thay = []

    def xu_ly(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/auth/login":
            import jwt, time
            t = jwt.encode({"exp": int(time.time()) + 900}, "k" * 32, algorithm="HS256")
            return httpx.Response(200, json={"access_token": t, "refresh_token": t, "expires_in": 900})
        thay.append((req.method, req.url.path, dict(req.url.params), req.headers.get("authorization")))
        if req.url.path == "/loi":
            return httpx.Response(503, json={"detail": "bận"})
        return httpx.Response(200, json={"items": []})

    ch = CauHinh(identity_url="http://id", content_url="http://ct", exam_url="http://ex",
                 email="a@b.vn", password="x" * 16)
    c = TestbankClient(ch, httpx.AsyncClient(transport=httpx.MockTransport(xu_ly)), KhoTokenBoNho())
    assert await c.lay("content", "/pool", {"subject": "TO", "grade": "06", "limit": 2000}) == {"items": []}
    m, p, params, auth = thay[0]
    assert (m, p, params) == ("GET", "/pool", {"subject": "TO", "grade": "06", "limit": "2000"})
    assert auth.startswith("Bearer ")
    try:
        await c.lay("content", "/loi")
    except TestbankLoi as e:
        assert e.tam_thoi is True
    else:
        raise AssertionError("phải ném TestbankLoi")


async def test_overview_khong_dem_luot_luyen_them_khong_xet_dat(client, session):
    """CMS /admin/overview: lượt luyện thêm dưới 3 câu chấm được (dat=False, không phải trượt)
    không làm tăng số lượt / số học sinh; lượt xét đạt thì có."""
    from tests.api.test_luyen_them import _admin

    hs, uid = await _hs(client, session)
    ad = await _admin(client, session)
    bai = await _bai(session)

    async def tong():
        return (await client.get("/admin/overview?ngay=7", headers=ad)).json()["tong"]["luot_lam"]

    truoc = await tong()
    session.add_all([QuizAttempt(user_id=uid, topic_id=bai.tid, diem=0, tong=2, dat=False,
                                 nguon="luyen_them") for _ in range(4)])
    await session.commit()
    b = (await client.get("/admin/overview?ngay=7", headers=ad)).json()
    assert b["tong"]["luot_lam"] == truoc
    assert all(x["topic_id"] != bai.tid for x in b["kho_nhat"])     # 4 lượt >= toi_thieu nhưng đều bị loại
    session.add(QuizAttempt(user_id=uid, topic_id=bai.tid, diem=1, tong=4, dat=False, nguon="luyen_them"))
    await session.commit()
    assert await tong() == truoc + 1

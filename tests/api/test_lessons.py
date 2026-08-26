import json
import uuid

from sqlalchemy import func, select

from app.db.models import CurriculumTopic, Grade, Subject, TopicContent, User


async def _auth(client) -> dict:
    email = f"les-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "An", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _seed_curriculum(session):
    """Tạo môn/khối/đơn vị RIÊNG (tên duy nhất) để test cô lập. Trả (mon, khoi, topic_ids)."""
    mon, khoi = f"MonTest-{uuid.uuid4().hex[:6]}", f"Khoi-{uuid.uuid4().hex[:6]}"
    subj = Subject(name=mon); grade = Grade(name=khoi)
    session.add_all([subj, grade]); await session.flush()
    topics = []
    units = [("Số tự nhiên", "Tập hợp số tự nhiên"),
             ("Số tự nhiên", "Tập hợp số tự nhiên"),   # trùng -> phải bị khử
             ("Số tự nhiên", "Số nguyên tố và hợp số"),
             ("Số nguyên", "Số nguyên âm")]
    for i, (m, d) in enumerate(units):
        t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id,
                            mach_noi_dung=m, don_vi_kien_thuc=d, order_index=i)
        session.add(t); topics.append(t)
    await session.flush()
    return mon, khoi, topics


async def test_curriculum_gom_mach_va_khu_trung(client, session):
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    await session.commit()
    groups = (await client.get(f"/curriculum?mon={mon}&khoi={khoi}", headers=h)).json()
    assert [g["mach"] for g in groups] == ["Số tự nhiên", "Số nguyên"]
    st = next(g for g in groups if g["mach"] == "Số tự nhiên")
    assert len(st["dv"]) == 2            # 3 dòng nhưng 1 trùng -> 2 đơn vị
    assert st["dv"][0]["trang_thai"] == "chua" and st["dv"][0]["co_noi_dung"] is False


async def test_lesson_chua_bien_soan_va_co_noi_dung(client, session):
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    tid = topics[2].id
    await session.commit()
    # chưa biên soạn
    r = (await client.get(f"/lessons/{tid}", headers=h)).json()
    assert r["trang_thai"] == "chua_bien_soan" and r["khai_niem"] == "" and r["minh_hoa"] == []
    # thêm nội dung -> trả về đủ 4 phần
    session.add(TopicContent(topic_id=tid, khai_niem="<p>ĐN</p>",
        minh_hoa_json=json.dumps([{"type": "video", "source": "ai"}]),
        vi_du_json=json.dumps([{"de": "VD", "giai": "GI"}]), trang_thai="published"))
    await session.commit()
    r2 = (await client.get(f"/lessons/{tid}", headers=h)).json()
    assert r2["khai_niem"] == "<p>ĐN</p>" and r2["vi_du"][0]["de"] == "VD"
    assert r2["minh_hoa"][0]["source"] == "ai" and r2["trang_thai"] == "published"


async def test_progress_upsert_va_me(client, session):
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    tid = topics[2].id
    await session.commit()
    # đánh dấu Đạt
    r = await client.post("/progress", json={"topic_id": tid, "trang_thai": "dat"}, headers=h)
    assert r.status_code == 200 and r.json()["trang_thai"] == "dat"
    me = (await client.get(f"/progress/me?mon={mon}&khoi={khoi}", headers=h)).json()
    assert me["dat"] == 1 and me["tong"] == 3 and 0 < me["overall"] <= 100
    # đơn vị vừa đánh dấu hiện 'dat' trong nhóm
    flat = [d for g in me["mach"] for d in g["dv"]]
    assert any(d["topic_id"] == tid and d["trang_thai"] == "dat" for d in flat)


async def test_progress_hop_le(client, session):
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    tid0 = topics[0].id  # lấy id TRƯỚC commit (sau commit ORM bị expire)
    await session.commit()
    assert (await client.post("/progress", json={"topic_id": tid0, "trang_thai": "bay"}, headers=h)).status_code == 400
    assert (await client.post("/progress", json={"topic_id": 999999, "trang_thai": "dat"}, headers=h)).status_code == 404
    assert (await client.get("/lessons/999999", headers=h)).status_code == 404


async def test_hoc_sinh_xem_duoc_hinh_vi_du(client, session):
    """HS phải nhận URL hình ĐÃ KÝ; `anh_prompt` là ghi chú của người soạn, không lộ ra."""
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    tid = topics[2].id
    session.add(TopicContent(topic_id=tid, khai_niem="<p>ĐN</p>", vi_du_json=json.dumps([
        {"de": "Hình bên", "giai": "…", "anh": "/video/files/vd.png",
         "anh_prompt": "flat triangle, no text"},
        {"de": "Ảnh ngoài", "giai": "…", "anh": "https://ngoai.vn/a.png"},
    ]), trang_thai="published"))
    await session.commit()

    v = (await client.get(f"/lessons/{tid}", headers=h)).json()["vi_du"]
    assert v[0]["anh"].startswith("/video/files/vd.png?exp=")   # ký -> phát được trong hạn
    assert "anh_prompt" not in v[0]
    assert v[1]["anh"] == "https://ngoai.vn/a.png"              # URL ngoài giữ nguyên


# ─────────────── Ôn tập chương / cuối kỳ (REQ §3.5) ───────────────

def _quiz(n: int, dap_an: int = 1) -> str:
    return json.dumps([{"q": f"Câu {i}", "o": ["A", "B", "C", "D"], "a": dap_an,
                        "lv": "de", "giai": f"giải {i}"} for i in range(n)])


async def test_de_on_tap_rai_deu_qua_cac_bai(client, session):
    """Lấy tuần tự sẽ ra đề toàn câu của bài đầu; phải rải vòng."""
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    # 3 đơn vị của mạch "Số tự nhiên" (1 trùng tên bị khử ở mục lục nhưng vẫn có id)
    st = [t for t in topics if t.mach_noi_dung == "Số tự nhiên"]
    for t in st:
        session.add(TopicContent(topic_id=t.id, quiz_json=_quiz(8)))
    await session.commit()

    r = await client.get(f"/on-tap/de?pham_vi=mach&gia_tri=Số tự nhiên&mon={mon}&khoi={khoi}",
                         headers=h)
    assert r.status_code == 200
    b = r.json()
    assert b["so_cau"] == 12                      # _SO_CAU_ON["mach"]
    # rải đều: 12 câu chia cho 3 bài -> mỗi bài 4 câu, không dồn vào 1 bài
    from collections import Counter
    dem = Counter(c["topic_id"] for c in b["cau"])
    assert sorted(dem.values()) == [4, 4, 4]
    # KHÔNG lộ đáp án ra client
    assert all("a" not in c and "giai" not in c for c in b["cau"])
    assert all(c["bai"] for c in b["cau"])        # có tên bài để HS biết câu của bài nào


async def test_de_on_tap_bao_ro_khi_chua_bai_nao_co_quiz(client, session):
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    await session.commit()
    r = await client.get(f"/on-tap/de?pham_vi=mach&gia_tri=Số nguyên&mon={mon}&khoi={khoi}",
                         headers=h)
    assert r.status_code == 409 and "chưa có bài kiểm tra nhanh" in r.json()["detail"]

    r2 = await client.get(f"/on-tap/de?pham_vi=mach&gia_tri=Không có mạch này"
                          f"&mon={mon}&khoi={khoi}", headers=h)
    assert r2.status_code == 404
    r3 = await client.get(f"/on-tap/de?pham_vi=sai&gia_tri=x&mon={mon}&khoi={khoi}", headers=h)
    assert r3.status_code == 400


async def test_nop_de_on_tap_cham_o_server_va_khong_ha_cap_don_vi(client, session):
    """Ôn tập là xem lại cả mạch — một câu sai không được làm bài đã 'dat' tụt lại."""
    from app.db.models import QuizAttempt, StudentProgress

    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    st = [t for t in topics if t.mach_noi_dung == "Số tự nhiên"]
    for t in st:
        session.add(TopicContent(topic_id=t.id, quiz_json=_quiz(8, dap_an=1)))
    await session.flush()
    # bài đầu đã ĐẠT trước khi ôn tập
    me = (await client.get("/auth/me", headers=h)).json()
    ids = [t.id for t in st]          # lấy id TRƯỚC commit (expire-on-commit)
    session.add(StudentProgress(user_id=me["id"], topic_id=ids[0], trang_thai="dat"))
    await session.commit()

    # trả lời SAI hết
    r = await client.post("/on-tap/submit", headers=h, json={
        "pham_vi": "mach", "gia_tri": "Số tự nhiên", "mon": mon, "khoi": khoi,
        "answers": [0] * 12})
    assert r.status_code == 200
    b = r.json()
    assert b["diem"] == 0 and b["tong"] == 12 and b["dat_yeu_cau"] is False
    assert len(b["ket_qua"]) == 12
    assert all(k["dap_an"] == 1 and k["giai"] for k in b["ket_qua"])   # đáp án + giải CHỈ trả sau khi nộp
    assert all(k["bai"] for k in b["ket_qua"])

    # đơn vị đã đạt vẫn đạt
    row = await session.scalar(select(StudentProgress).filter_by(
        user_id=me["id"], topic_id=ids[0]))
    assert row.trang_thai == "dat"
    # nhưng có ghi lại lượt làm cho từng bài để hồ sơ thấy được
    n = await session.scalar(select(func.count()).select_from(QuizAttempt)
                             .where(QuizAttempt.user_id == me["id"],
                                    QuizAttempt.topic_id.in_(ids)))
    assert n == 3


async def test_nop_de_on_tap_dung_het_thi_dat_va_cong_xp(client, session):
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    for t in [x for x in topics if x.mach_noi_dung == "Số tự nhiên"]:
        session.add(TopicContent(topic_id=t.id, quiz_json=_quiz(8, dap_an=2)))
    await session.commit()

    r = await client.post("/on-tap/submit", headers=h, json={
        "pham_vi": "mach", "gia_tri": "Số tự nhiên", "mon": mon, "khoi": khoi,
        "answers": [2] * 12})
    b = r.json()
    assert b["diem"] == 12 and b["dat_yeu_cau"] is True and b["xp"] > 0


async def test_on_tap_bao_so_cau_THAT_gom_duoc_khong_hua_suong(client, session):
    """Bài chưa có đề thì không góp câu — không được hứa 12 rồi đưa ra 8."""
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    st = [t for t in topics if t.mach_noi_dung == "Số tự nhiên"]
    session.add(TopicContent(topic_id=st[0].id, khai_niem="<p>x</p>", quiz_json=_quiz(8)))
    await session.commit()

    b = (await client.get(f"/on-tap?pham_vi=mach&gia_tri=Số tự nhiên&mon={mon}&khoi={khoi}",
                          headers=h)).json()
    assert b["so_cau_toi_da"] == 12          # chỉ tiêu
    assert b["so_cau_de"] == 8               # thật gom được
    assert b["so_bai_co_de"] == 1 and b["so_bai"] == 2


async def test_stats_tra_tien_do_TUNG_mach_va_phan_tram_ycd(client, session):
    """Vòng tiến độ phải theo mạch của BÀI ĐANG MỞ, nên /me/stats trả cả danh sách.

    Trước đây chỉ trả `current_mach` = mạch chưa xong đầu tiên, nên mở bài ở mạch
    khác rồi quay lại thì vòng vẫn đứng ở % của mạch cũ.
    """
    from app.db.models import Blueprint, BlueprintCell, StudentProgress

    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    st = [t for t in topics if t.mach_noi_dung == "Số tự nhiên"]
    sn = [t for t in topics if t.mach_noi_dung == "Số nguyên"]
    me = (await client.get("/auth/me", headers=h)).json()

    bp = Blueprint(subject_id=st[0].subject_id, grade_id=st[0].grade_id, semester="hk1")
    session.add(bp); await session.flush()
    # 3 yêu cầu cần đạt cho đơn vị đầu, 1 cho đơn vị của mạch Số nguyên
    for t, n in ((st[0], 3), (sn[0], 1)):
        for i in range(n):
            session.add(BlueprintCell(blueprint_id=bp.id, muc_do="de", nang_luc="NL",
                                      yeu_cau_can_dat=f"YCĐ {t.id}-{i}", topic_id=t.id,
                                      dang_thuc="TN", ti_le=0.25, nhom_ti_le=i))
    session.add(StudentProgress(user_id=me["id"], topic_id=st[0].id, trang_thai="dat"))
    await session.commit()

    b = (await client.get(f"/me/stats?mon={mon}&khoi={khoi}", headers=h)).json()
    ten_mach = [m["mach"] for m in b["mach"]]
    assert "Số tự nhiên" in ten_mach and "Số nguyên" in ten_mach
    # mạch "Số tự nhiên" có 2 đơn vị (1 trùng đã khử), đạt 1 -> 50%
    assert next(m for m in b["mach"] if m["mach"] == "Số tự nhiên")["phan_tram"] == 50
    assert next(m for m in b["mach"] if m["mach"] == "Số nguyên")["phan_tram"] == 0

    # % yêu cầu cần đạt: 3/4 ô thuộc đơn vị đã đạt
    assert b["ycd_tong"] == 4 and b["ycd_dat"] == 3 and b["ycd_phan_tram"] == 75


async def test_stats_khong_co_ma_tran_thi_ycd_bang_0_khong_no(client, session):
    h = await _auth(client)
    mon, khoi, topics = await _seed_curriculum(session)
    await session.commit()
    b = (await client.get(f"/me/stats?mon={mon}&khoi={khoi}", headers=h)).json()
    assert b["ycd_tong"] == 0 and b["ycd_phan_tram"] == 0


async def test_on_tap_gia_tri_rong_bao_400_ro_rang(client, session):
    """`gia_tri` rỗng từng rơi vào 404 "phạm vi không có đơn vị nào" — đọc vào
    tưởng thiếu dữ liệu, trong khi lỗi là client gửi tham số rỗng."""
    h = await _auth(client)
    for pv in ("mach", "hoc_ky"):
        for ep in ("/on-tap", "/on-tap/de"):
            r = await client.get(f"{ep}?pham_vi={pv}&gia_tri=", headers=h)
            assert r.status_code == 400, f"{ep} {pv}: {r.status_code}"
            assert "gia_tri" in r.json()["detail"]
    r2 = await client.post("/on-tap/submit", headers=h, json={
        "pham_vi": "mach", "gia_tri": "   ", "answers": []})
    assert r2.status_code == 400

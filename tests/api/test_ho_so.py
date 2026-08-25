"""§3.6 — Hồ sơ học tập: phiên học, biểu đồ, yêu cầu cần đạt."""
import uuid

from app.db.models import CurriculumTopic, Grade, Subject


async def _hs(client):
    e = f"hs-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": e, "password": "matkhau123", "name": "HS", "role": "hoc_sinh"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _topic(session):
    subj = Subject(name=f"M-{uuid.uuid4().hex[:6]}"); gr = Grade(name=f"K-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, gr]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="M",
                        don_vi_kien_thuc="Đơn vị A", order_index=0)
    session.add(t); await session.flush()
    # Lấy MỌI thứ cần dùng TRƯỚC commit: sau commit thuộc tính bị expire, đọc lại
    # là lazy load ngoài greenlet -> MissingGreenlet.
    tid, mon, khoi = t.id, subj.name, gr.name
    await session.commit()
    return mon, khoi, tid


async def test_ping_cong_don_vao_cung_phien(client, session):
    """Ping nhiều lần trong một lượt học -> MỘT phiên, số giây cộng dồn."""
    h = await _hs(client)
    mon, khoi, tid = await _topic(session)
    for _ in range(3):
        r = await client.post("/me/phien", headers=h, json={"topic_id": tid, "giay": 30})
        assert r.status_code == 200
    assert r.json()["so_giay_phien"] == 90

    d = (await client.get("/me/thoi-gian", headers=h)).json()
    assert d["so_phien"] == 1 and d["hom_nay_phut"] == 2   # 90s -> 2 phút (round)


async def test_ping_chan_tran_khong_tin_client(client, session):
    """Client khai 3600 giây một lần -> chặn ở trần, không phải học thật."""
    h = await _hs(client)
    mon, khoi, tid = await _topic(session)
    r = await client.post("/me/phien", headers=h, json={"topic_id": tid, "giay": 3600})
    assert r.json()["so_giay_phien"] == 120     # _TRAN_PING


async def test_bieu_do_co_du_ngay_ke_ca_ngay_khong_hoc(client, session):
    """Ngày nghỉ vẫn phải có điểm 0 — thiếu thì đường nối tắt, đọc thành có học."""
    from datetime import date

    h = await _hs(client)
    mon, khoi, tid = await _topic(session)
    await client.post("/me/phien", headers=h, json={"topic_id": tid, "giay": 60})
    d = (await client.get("/me/thoi-gian?ngay=14", headers=h)).json()
    assert len(d["bieu_do"]) == 14
    assert d["bieu_do"][-1]["ngay"] == str(date.today())
    assert d["bieu_do"][-1]["hom_nay"] is True
    assert sum(1 for x in d["bieu_do"] if x["phut"] == 0) == 13
    assert d["muc_tieu_phut"] == 20 and d["dat_muc_tieu"] is False


async def test_lich_su_co_ten_bai_va_so_cau_hoi(client, session):
    h = await _hs(client)
    mon, khoi, tid = await _topic(session)
    await client.post("/me/phien", headers=h, json={"topic_id": tid, "giay": 60})
    d = (await client.get("/me/thoi-gian", headers=h)).json()
    assert d["lich_su"][0]["ten"] == "Đơn vị A" and d["lich_su"][0]["so_hoi"] == 0


async def test_ycd_giu_dung_thu_tu_ma_tran(client, session):
    """§3.6 khối 4 — KHÔNG sắp lại theo số lần sai."""
    from app.db.models import Blueprint, BlueprintCell

    h = await _hs(client)
    mon, khoi, tid = await _topic(session)
    from sqlalchemy import select

    bp = Blueprint(
        subject_id=await session.scalar(select(Subject.id).filter_by(name=mon)),
        grade_id=await session.scalar(select(Grade.id).filter_by(name=khoi)),
        semester="hk1")
    session.add(bp); await session.flush()
    for i, y in enumerate(["YCD một", "YCD hai", "YCD ba"]):
        session.add(BlueprintCell(blueprint_id=bp.id, muc_do="nhan_biet", nang_luc="NL",
                                  yeu_cau_can_dat=y, topic_id=tid, dang_thuc="TN",
                                  ti_le=0.3, nhom_ti_le=i))
    await session.commit()

    d = (await client.get(f"/me/ycd?mon={mon}&khoi={khoi}", headers=h)).json()
    ds = d["mach"][0]["ycd"]
    assert [x["ycd"] for x in ds] == ["YCD một", "YCD hai", "YCD ba"]
    assert ds[0]["don_vi"] == "Đơn vị A" and ds[0]["trang_thai"] == "chua"


async def test_on_tap_mach_gom_bai_va_noi_that_con_bao_nhieu_chua_xong(client, session):
    """§3.5 — nói thẳng "còn k bài chưa học xong", không im lặng để em tưởng đã đủ."""
    import json as _j
    from app.db.models import TopicContent

    h = await _hs(client)
    subj = Subject(name=f"M-{uuid.uuid4().hex[:6]}"); gr = Grade(name=f"K-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, gr]); await session.flush()
    ts = []
    for i, ten in enumerate(["Bài A", "Bài B", "Bài A"]):     # "Bài A" TRÙNG -> phải khử
        t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="Số tự nhiên",
                            don_vi_kien_thuc=ten, order_index=i)
        session.add(t); ts.append(t)
    await session.flush()
    session.add(TopicContent(topic_id=ts[0].id,
                             khai_niem="<p>x</p><blockquote>Số nguyên tố có hai ước</blockquote>"))
    mon, khoi = subj.name, gr.name
    await session.commit()

    b = (await client.get(f"/on-tap?pham_vi=mach&gia_tri=Số tự nhiên&mon={mon}&khoi={khoi}",
                          headers=h)).json()
    assert b["so_bai"] == 2                      # "Bài A" trùng đã khử
    assert b["chua_xong"] == 2                   # chưa đạt bài nào
    # `so_cau_de` là số câu THẬT gom được, `so_cau_toi_da` là chỉ tiêu. Ở đây
    # không bài nào có `quiz_json` nên chưa gom được câu nào — trước đây trả
    # thẳng chỉ tiêu 12 và giao diện hứa "12 câu" rồi đưa ra 0.
    assert b["so_cau_toi_da"] == 12 and b["so_cau_de"] == 0
    assert b["so_bai_co_de"] == 0
    assert b["can_nho"][0]["y"] == "Số nguyên tố có hai ước"


async def test_on_tap_cuoi_ky_30_cau_va_pham_vi_la_bi_chan(client, session):
    h = await _hs(client)
    subj = Subject(name=f"M-{uuid.uuid4().hex[:6]}"); gr = Grade(name=f"K-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, gr]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="M",
                        don_vi_kien_thuc="A", order_index=0, hoc_ky="hk1")
    session.add(t)
    mon, khoi = subj.name, gr.name
    await session.commit()

    b = (await client.get(f"/on-tap?pham_vi=hoc_ky&gia_tri=hk1&mon={mon}&khoi={khoi}",
                          headers=h)).json()
    assert b["so_cau_toi_da"] == 30 and b["so_cau_de"] == 0   # chưa bài nào có đề
    r = await client.get(f"/on-tap?pham_vi=bịa&gia_tri=x&mon={mon}&khoi={khoi}", headers=h)
    assert r.status_code == 400


async def test_lich_su_du_3_nhan_kiem_tra_doc_x_y_dang_hoc(client, session):
    """§3.6 khối 3 — "✅ Kiểm tra d/t", "Đọc x/y phần", "● đang học"."""
    import json as _j
    from app.db.models import TopicContent

    h = await _hs(client)
    subj = Subject(name=f"M-{uuid.uuid4().hex[:6]}"); gr = Grade(name=f"K-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, gr]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="M",
                        don_vi_kien_thuc="Bài A", order_index=0)
    session.add(t); await session.flush()
    tid = t.id
    # Bài có 3 phần CÓ NỘI DUNG -> mẫu số phải là 3, không phải 7
    session.add(TopicContent(topic_id=tid, trang_thai="published",
                             khai_niem="<p>kt</p>", khoi_dong="<p>kd</p>", bai_tap="<p>bt</p>",
                             quiz_json=_j.dumps([{"q": "?", "o": ["a", "b"], "a": 1, "lv": "de"}])))
    await session.commit()

    await client.post("/me/phien", headers=h,
                      json={"topic_id": tid, "giay": 60, "phan_doc": ["khoi_dong", "kien_thuc"]})
    await client.post("/quiz/submit", headers=h, json={"topic_id": tid, "answers": [1]})

    ls = (await client.get("/me/thoi-gian", headers=h)).json()["lich_su"][0]
    assert ls["doc_x"] == 2 and ls["doc_y"] == 3          # 2/3 phần, KHÔNG phải /7
    assert ls["quiz"] == {"diem": 1, "tong": 1, "dat": True}
    assert ls["dang_hoc"] is True                          # vừa ping xong


async def test_phan_doc_hop_nhat_khong_ghi_de(client, session):
    """Cuộn lên trên -> client gửi danh sách ngắn hơn; KHÔNG được mất phần đã đọc."""
    h = await _hs(client)
    mon, khoi, tid = await _topic(session)
    await client.post("/me/phien", headers=h,
                      json={"topic_id": tid, "giay": 30, "phan_doc": ["khoi_dong", "kien_thuc"]})
    await client.post("/me/phien", headers=h,
                      json={"topic_id": tid, "giay": 30, "phan_doc": ["khoi_dong"]})
    ls = (await client.get("/me/thoi-gian", headers=h)).json()["lich_su"][0]
    assert ls["doc_x"] == 2      # vẫn 2, không tụt về 1


async def test_phan_doc_luoc_id_la(client, session):
    """Client gửi id bịa -> không vào DB, mẫu số không bị sai."""
    h = await _hs(client)
    mon, khoi, tid = await _topic(session)
    await client.post("/me/phien", headers=h,
                      json={"topic_id": tid, "giay": 30,
                            "phan_doc": ["kien_thuc", "bịa", "<script>"]})
    ls = (await client.get("/me/thoi-gian", headers=h)).json()["lich_su"][0]
    assert ls["doc_x"] == 1


async def test_nhan_kiem_tra_thuoc_dung_phien_khong_gan_lan(client, session):
    """Kết quả hôm nay KHÔNG được hiện trên phiên tuần trước."""
    import json as _j
    from datetime import datetime, timedelta
    from app.db.models import QuizAttempt, StudySession, TopicContent

    h = await _hs(client)
    from sqlalchemy import select as _sel
    from app.db.models import User
    subj = Subject(name=f"M-{uuid.uuid4().hex[:6]}"); gr = Grade(name=f"K-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, gr]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="M",
                        don_vi_kien_thuc="A", order_index=0)
    session.add(t); await session.flush()
    tid = t.id
    session.add(TopicContent(topic_id=tid, khai_niem="<p>x</p>", trang_thai="published"))
    await session.commit()

    # Ping -> tạo phiên HÔM NAY
    await client.post("/me/phien", headers=h, json={"topic_id": tid, "giay": 60})
    uid = await session.scalar(_sel(StudySession.user_id).where(StudySession.topic_id == tid))
    # Phiên CŨ 5 ngày trước, KHÔNG có lần nộp nào trong khoảng đó
    cu = datetime.now() - timedelta(days=5)
    old = StudySession(user_id=uid, topic_id=tid, so_giay=300)
    session.add(old); await session.flush()
    old.mo_luc, old.dong_luc = cu, cu
    # Lần nộp HÔM NAY
    session.add(QuizAttempt(user_id=uid, topic_id=tid, diem=2, tong=4, dat=False))
    await session.commit()

    ls = (await client.get("/me/thoi-gian", headers=h)).json()["lich_su"]
    hom_nay = next(x for x in ls if x["dang_hoc"])
    phien_cu = next(x for x in ls if not x["dang_hoc"])
    assert hom_nay["quiz"] == {"diem": 2, "tong": 4, "dat": False}
    assert phien_cu["quiz"] is None      # KHÔNG gán lẫn


async def test_doc_x_khong_duoc_lon_hon_doc_y_khi_phan_bi_an(client, session):
    """Chuyên gia ẩn bớt phần sau khi HS đã đọc -> không được hiện "Đọc 4/3 phần"."""
    import json as _j
    from datetime import datetime, timedelta

    from app.db.models import StudySession, TopicContent

    h = await _hs(client)
    mon, khoi, tid = await _topic(session)
    # Bài chỉ HIỆN 2 phần (khởi động bị ẩn), nhưng HS đã đọc cả 3
    session.add(TopicContent(
        topic_id=tid, khoi_dong="<p>kd</p>", khai_niem="<p>kt</p>", luyen_tap="<p>lt</p>",
        bo_cuc_json=_j.dumps([{"id": "khoi_dong", "an": True},
                              {"id": "kien_thuc"}, {"id": "luyen_tap"}])))
    me = (await client.get("/auth/me", headers=h)).json()
    now = datetime.now()
    session.add(StudySession(user_id=me["id"], topic_id=tid, mo_luc=now - timedelta(minutes=20),
                             dong_luc=now - timedelta(minutes=1), so_giay=1200,
                             phan_doc_json=_j.dumps(["khoi_dong", "kien_thuc", "luyen_tap"])))
    await session.commit()

    d = (await client.get("/me/thoi-gian", headers=h)).json()
    ph = next(x for x in d["lich_su"] if x["topic_id"] == tid)
    assert ph["doc_y"] == 2
    assert ph["doc_x"] == 2, "phần đã ẩn không được tính vào tử số"
    assert ph["doc_x"] <= ph["doc_y"]
    assert ph["dang_hoc"] is True        # phiên vừa đóng 1 phút trước

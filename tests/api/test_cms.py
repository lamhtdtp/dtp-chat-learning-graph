import io
import json
import uuid

from sqlalchemy import select

from app.db.models import CurriculumTopic, Grade, Subject


async def _auth(client, role="giao_vien") -> dict:
    email = f"cms-{uuid.uuid4().hex[:8]}@vd.vn"
    r = await client.post("/auth/register", json={
        "email": email, "password": "matkhau123", "name": "GV", "role": role})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _seed(session):
    mon, khoi = f"MonC-{uuid.uuid4().hex[:6]}", f"KhoiC-{uuid.uuid4().hex[:6]}"
    subj = Subject(name=mon); grade = Grade(name=khoi)
    session.add_all([subj, grade]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id,
                        mach_noi_dung="Số tự nhiên", don_vi_kien_thuc="Số nguyên tố", order_index=0)
    session.add(t); await session.flush()
    return mon, khoi, t.id


async def test_cms_chi_tac_gia(client, session):
    hs = await _auth(client, "hoc_sinh")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    assert (await client.get(f"/cms/curriculum?mon={mon}&khoi={khoi}", headers=hs)).status_code == 403
    assert (await client.get(f"/cms/topics/{tid}", headers=hs)).status_code == 403


async def test_cms_save_va_completeness(client, session):
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    # trống -> 0/4
    t0 = (await client.get(f"/cms/topics/{tid}", headers=gv)).json()
    assert t0["completeness"]["done"] == 0 and t0["trang_thai"] == "draft"
    # lưu 2 phần -> 2/4, xuất bản
    r = await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>Số nguyên tố…</p>",
        "minh_hoa": [{"type": "video", "url": "", "caption": "", "source": "ai"}],
        "vi_du": [], "day": {"muc_tieu": "MT"}, "nguon": None, "trang_thai": "published"})
    assert r.status_code == 200 and r.json()["completeness"]["done"] == 2
    # HS thấy nội dung đã xuất bản qua /lessons
    hs = await _auth(client, "hoc_sinh")
    les = (await client.get(f"/lessons/{tid}", headers=hs)).json()
    assert les["trang_thai"] == "published" and les["khai_niem"] == "<p>Số nguyên tố…</p>"


async def test_cms_trang_thai_khong_hop_le_400(client, session):
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    r = await client.put(f"/cms/topics/{tid}", headers=gv, json={"trang_thai": "xong"})
    assert r.status_code == 400


async def test_cms_nhap_chua_xuat_ban_hs_khong_thay(client, session):
    gv = await _auth(client, "giao_vien")
    hs = await _auth(client, "hoc_sinh")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>nháp</p>", "minh_hoa": [], "vi_du": [], "trang_thai": "draft"})
    les = (await client.get(f"/lessons/{tid}", headers=hs)).json()
    assert les["trang_thai"] == "chua_bien_soan" and les["khai_niem"] == ""


def _chunk(page_no: int, content: str):
    """RetrievedChunk tối thiểu để mock retriever (không cần Qdrant thật)."""
    from app.retrieval.retriever import RetrievedChunk

    return RetrievedChunk(content=content, score=0.9, chuong_so=1, bai_so=1,
                          page_no=page_no, tap=1, loai_noi_dung="ly_thuyet", nguon="sgk")


def _mock_ai(mocker, *, chunks, khai_niem="<p>AI nháp</p>", anh=None, video=None):
    """Mock LLM + retriever cho luồng ai-ingest. Trả mock của gateway.complete."""
    payload = {"khai_niem": khai_niem, "vi_du": [{"de": "VD1", "giai": "GIẢI1"}]}
    if anh is not None:
        payload["anh"] = anh
    if video is not None:
        payload["video"] = video
    complete = mocker.AsyncMock(return_value=json.dumps(payload, ensure_ascii=False))
    mocker.patch("app.lessons.ingest.gateway.complete", complete)
    # retriever phải mock: nó gọi API embedding thật + Qdrant thật.
    mocker.patch("app.lessons.ingest.retriever.retrieve", mocker.AsyncMock(return_value=chunks))
    return complete


async def test_cms_ai_ingest_bam_sgk(client, session, mocker):
    """Có ngữ liệu SGK -> ngữ liệu + số trang đi vào prompt, thieu_sgk=False."""
    complete = _mock_ai(mocker, chunks=[_chunk(45, "Số nguyên tố chỉ có hai ước."),
                                        _chunk(46, "Hợp số có nhiều hơn hai ước.")])
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    r = await client.post(f"/cms/topics/{tid}/ai-ingest", headers=gv, json={"nguon": "trích SGK"})
    body = r.json()
    assert body["khai_niem"] == "<p>AI nháp</p>" and body["vi_du"][0]["de"] == "VD1"
    assert body["thieu_sgk"] is False and body["trang_sgk"] == [45, 46]
    # Prompt thật sự chứa ngữ liệu SGK có nhãn [tr.N] + tư liệu chuyên gia dán vào.
    prompt = complete.await_args.kwargs["messages"][0]["content"]
    assert "[tr.45] Số nguyên tố chỉ có hai ước." in prompt
    assert "QUY TẮC BÁM SÁCH" in prompt and "trích SGK" in prompt
    # ingest KHÔNG tự lưu — topic vẫn trống
    assert (await client.get(f"/cms/topics/{tid}", headers=gv)).json()["completeness"]["done"] == 0


def test_slug_ten_hien_thi_sang_gia_tri_qdrant():
    """Map bỏ dấu phải khớp payload Qdrant — lệch là grounding về 0 mà không báo lỗi."""
    from app.lessons.ingest import _slug

    assert _slug("Toán") == "toan"
    assert _slug("Tiếng Anh") == "tieng_anh"
    assert _slug("Lớp 6") == "lop_6"
    assert _slug("  Ngữ văn  ") == "ngu_van"


async def test_cms_ai_ingest_retrieve_dung_mon_khoi(client, session, mocker):
    """Truy vấn Qdrant phải dùng mon/khoi đã bỏ dấu, và query gồm đơn vị + mạch."""
    complete = mocker.AsyncMock(return_value=json.dumps({"khai_niem": "<p>x</p>", "vi_du": []}))
    mocker.patch("app.lessons.ingest.gateway.complete", complete)
    retrieve = mocker.patch("app.lessons.ingest.retriever.retrieve", mocker.AsyncMock(return_value=[]))

    gv = await _auth(client, "giao_vien")
    # Tên hiển thị CÓ DẤU, đúng như seed thật (Subject "Toán", Grade "Lớp 6").
    suffix = uuid.uuid4().hex[:6]
    subj = Subject(name=f"Toán{suffix}"); grade = Grade(name=f"Lớp 6{suffix}")
    session.add_all([subj, grade]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=grade.id, mach_noi_dung="Số tự nhiên",
                        don_vi_kien_thuc="Số nguyên tố", order_index=0)
    session.add(t); await session.flush()
    tid = t.id   # lấy trước commit: sau commit thuộc tính bị expire -> lazy load lỗi
    await session.commit()

    await client.post(f"/cms/topics/{tid}/ai-ingest", headers=gv, json={"media": False})
    kw = retrieve.await_args.kwargs
    assert kw["mon"] == f"toan{suffix}".lower() and kw["khoi"] == f"lop_6{suffix}".lower()
    assert "Số nguyên tố" in retrieve.await_args.args[0]
    assert "Số tự nhiên" in retrieve.await_args.args[0]


async def test_cms_ai_ingest_thieu_sgk_van_soan_va_canh_bao(client, session, mocker):
    """Không retrieve được gì -> vẫn có nháp, nhưng gắn cờ thieu_sgk + cấm bịa [tr.N]."""
    complete = _mock_ai(mocker, chunks=[])
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    body = (await client.post(f"/cms/topics/{tid}/ai-ingest", headers=gv, json={})).json()
    assert body["thieu_sgk"] is True and body["trang_sgk"] == []
    assert body["khai_niem"] == "<p>AI nháp</p>"   # vẫn soạn được, không chặn tác giả
    assert "KHÔNG bịa số trang" in complete.await_args.kwargs["messages"][0]["content"]


async def test_cms_ai_ingest_sinh_anh_va_dat_hang_video(client, session, mocker):
    """media=True -> ảnh sinh thật vào storage, video tạo VideoJob + đẩy hàng đợi."""
    from app.db.models import VideoJob

    _mock_ai(mocker, chunks=[_chunk(45, "ngữ liệu")],
             anh=[{"caption": "Sàng Eratosthenes", "prompt": "clean diagram, no text"}],
             video={"chu_de": "số nguyên tố là gì", "caption": "Video 60s"})
    mocker.patch("app.lessons.media.gateway.generate_image",
                 mocker.AsyncMock(return_value=b"\x89PNG_fake"))
    delay = mocker.patch("app.ingestion.celery_app.render_video_task.delay")

    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    mh = (await client.post(f"/cms/topics/{tid}/ai-ingest", headers=gv, json={})).json()["minh_hoa"]

    img = next(m for m in mh if m["type"] == "image")
    assert img["source"] == "ai" and img["url"].startswith("/video/files/")
    assert img["caption"] == "Sàng Eratosthenes"
    # url thô để lưu, url_xem đã ký để xem -> hai giá trị khác nhau
    assert img["url_xem"].startswith(img["url"] + "?exp=") and "sig=" in img["url_xem"]

    vid = next(m for m in mh if m["type"] == "video")
    assert vid["url"] is None and vid["concept_key"].startswith("free:")
    job = await session.scalar(select(VideoJob).filter_by(concept_key=vid["concept_key"]))
    assert job is not None and job.status == "QUEUED"
    delay.assert_called_once_with(job_id=job.id)


async def test_cms_ai_ingest_media_loi_khong_lam_vo_nhap(client, session, mocker):
    """Sinh ảnh lỗi -> vẫn trả nháp chữ, kèm lý do trong loi_media."""
    from app.llm.gateway import LLMUnavailable

    _mock_ai(mocker, chunks=[_chunk(45, "ngữ liệu")],
             anh=[{"caption": "H", "prompt": "p"}], video=None)
    mocker.patch("app.lessons.media.gateway.generate_image",
                 mocker.AsyncMock(side_effect=LLMUnavailable("429")))
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    body = (await client.post(f"/cms/topics/{tid}/ai-ingest", headers=gv, json={})).json()
    assert body["khai_niem"] == "<p>AI nháp</p>"      # nháp chữ vẫn còn
    assert body["minh_hoa"] == [] and len(body["loi_media"]) == 1


async def test_cms_ai_ingest_media_false_khong_goi_sinh_anh(client, session, mocker):
    """media=False -> không tốn lần gọi model sinh ảnh."""
    _mock_ai(mocker, chunks=[_chunk(45, "x")], anh=[{"caption": "H", "prompt": "p"}])
    gen = mocker.patch("app.lessons.media.gateway.generate_image", mocker.AsyncMock())
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    body = (await client.post(f"/cms/topics/{tid}/ai-ingest", headers=gv,
                              json={"media": False})).json()
    assert body["minh_hoa"] == [] and gen.await_count == 0


async def test_cms_luu_khong_ghi_url_xem_vao_db(client, session):
    """url_xem là URL có chữ ký, hết hạn -> KHÔNG được lọt vào nội dung lưu."""
    from app.db.models import TopicContent

    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>x</p>", "vi_du": [], "trang_thai": "draft",
        "minh_hoa": [{"type": "image", "url": "/video/files/a.png", "caption": "H",
                      "source": "ai", "url_xem": "/video/files/a.png?exp=1&sig=deadbeef",
                      "rac": "khoá lạ"}]})
    c = await session.scalar(select(TopicContent).filter_by(topic_id=tid))
    luu = json.loads(c.minh_hoa_json)[0]
    assert luu == {"type": "image", "url": "/video/files/a.png", "caption": "H", "source": "ai"}


async def test_video_da_render_xong_thi_hien_url(client, session, mocker):
    """Video AI lưu với url=None: khi job DONE, đọc lại nội dung phải có url."""
    from app.config import settings
    from app.db.models import VideoJob

    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    key = "free:ZmFrZQ==::" + settings.sgk_version
    session.add(VideoJob(concept_key=key, sgk_version=settings.sgk_version,
                         status="DONE", video_url="/video/files/xong.mp4"))
    await session.commit()
    await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>x</p>", "vi_du": [], "trang_thai": "published",
        "minh_hoa": [{"type": "video", "url": None, "source": "ai", "concept_key": key}]})

    mh = (await client.get(f"/cms/topics/{tid}", headers=gv)).json()["minh_hoa"]
    assert mh[0]["url"] == "/video/files/xong.mp4"
    # HS cũng thấy, và URL phục vụ HS phải được ký
    hs = await _auth(client, "hoc_sinh")
    les = (await client.get(f"/lessons/{tid}", headers=hs)).json()
    assert les["minh_hoa"][0]["url"].startswith("/video/files/xong.mp4?exp=")


async def test_co_ai_soan_khong_suy_tu_chuoi_trong_nguon(client, session):
    """Trích đoạn SGK viết hoa chứa "HAI" KHÔNG được gắn nhãn AI (lỗi của cách cũ
    dò `"AI" in c.nguon`); cờ chỉ bật khi ai_soan=true."""
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>x</p>", "vi_du": [], "trang_thai": "draft",
        "nguon": "SỐ NGUYÊN TỐ CHỈ CÓ HAI ƯỚC"})
    dv = (await client.get(f"/cms/curriculum?mon={mon}&khoi={khoi}", headers=gv)).json()[0]["dv"][0]
    assert dv["ai"] is False

    # Luồng "Nạp sách bằng AI" đặt cờ tường minh -> mới hiện nhãn.
    await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>x</p>", "vi_du": [], "trang_thai": "draft", "ai_soan": True})
    dv = (await client.get(f"/cms/curriculum?mon={mon}&khoi={khoi}", headers=gv)).json()[0]["dv"][0]
    assert dv["ai"] is True


async def test_luu_khong_gui_ai_soan_thi_giu_nguyen_co(client, session):
    """Trình soạn không gửi ai_soan -> cờ cũ phải còn, không bị lưu đè thành False."""
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>a</p>", "vi_du": [], "trang_thai": "draft", "ai_soan": True})
    await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>đã sửa tay</p>", "vi_du": [], "trang_thai": "draft"})
    dv = (await client.get(f"/cms/curriculum?mon={mon}&khoi={khoi}", headers=gv)).json()[0]["dv"][0]
    assert dv["ai"] is True


async def test_nguon_qua_dai_bi_chan(client, session):
    """Chặn cả khi lưu lẫn khi ai-ingest — nguon đi thẳng vào prompt."""
    from app.config import settings

    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    qua_dai = "x" * (settings.cms_nguon_max_chars + 1)
    r = await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "", "vi_du": [], "trang_thai": "draft", "nguon": qua_dai})
    assert r.status_code == 400 and "Tư liệu nguồn dài" in r.json()["detail"]
    r = await client.post(f"/cms/topics/{tid}/ai-ingest", headers=gv, json={"nguon": qua_dai})
    assert r.status_code == 400
    # đúng biên thì vẫn lưu được
    r = await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "", "vi_du": [], "trang_thai": "draft",
        "nguon": "x" * settings.cms_nguon_max_chars})
    assert r.status_code == 200


async def test_cms_limits_tra_dung_gioi_han(client, session):
    from app.config import settings

    gv = await _auth(client, "giao_vien")
    r = await client.get("/cms/limits", headers=gv)
    assert r.status_code == 200 and r.json() == {"nguon_max_chars": settings.cms_nguon_max_chars}
    hs = await _auth(client, "hoc_sinh")
    assert (await client.get("/cms/limits", headers=hs)).status_code == 403


async def test_hs_khong_nhan_nguon_tac_gia_thi_co(client, session):
    """`nguon` là tư liệu nội bộ của chuyên gia — không đẩy xuống client HS."""
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    await client.put(f"/cms/topics/{tid}", headers=gv, json={
        "khai_niem": "<p>x</p>", "vi_du": [], "trang_thai": "published",
        "nguon": "ghi chú nội bộ của chuyên gia"})
    hs = await _auth(client, "hoc_sinh")
    assert (await client.get(f"/lessons/{tid}", headers=hs)).json()["nguon"] is None
    assert (await client.get(f"/lessons/{tid}", headers=gv)).json()["nguon"] == "ghi chú nội bộ của chuyên gia"


async def test_cms_upload_video(client, session):
    gv = await _auth(client, "giao_vien")
    mon, khoi, tid = await _seed(session)
    await session.commit()
    files = {"file": ("clip.mp4", io.BytesIO(b"\x00\x01fakevideo"), "video/mp4")}
    r = await client.post(f"/cms/topics/{tid}/video?caption=Minh+hoa", headers=gv, files=files)
    assert r.status_code == 200
    mh = r.json()["minh_hoa"]
    assert mh[-1]["type"] == "video" and mh[-1]["source"] == "expert"
    assert mh[-1]["url"].startswith("/video/files/")
    # định dạng sai -> 400
    bad = {"file": ("x.txt", io.BytesIO(b"abc"), "text/plain")}
    assert (await client.post(f"/cms/topics/{tid}/video", headers=gv, files=bad)).status_code == 400

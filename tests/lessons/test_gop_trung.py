"""Gộp đơn vị kiến thức trùng — không được làm mất bài soạn hay bài học sinh đã làm."""
import json
import uuid

from sqlalchemy import func, select

from app.db.models import (Blueprint, BlueprintCell, CurriculumTopic, Grade,
                           QuizAttempt, StudentProgress, Subject, TopicContent, User)
from app.lessons import gop_trung


async def _mon_khoi(session):
    subj = Subject(name=f"Mon-{uuid.uuid4().hex[:6]}")
    gr = Grade(name=f"Khoi-{uuid.uuid4().hex[:6]}")
    session.add_all([subj, gr]); await session.flush()
    return subj, gr


def _dv(subj, gr, ten, mach="Mạch A", **kw):
    return CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung=mach,
                           don_vi_kien_thuc=ten, order_index=0, **kw)


async def test_tim_trung_gom_theo_ten_chuan_hoa(db_session):
    subj, gr = await _mon_khoi(db_session)
    goc = _dv(subj, gr, "Hình có trục đối xứng", "Tính đối xứng của hình phẳng", hoc_ky="hk1")
    # bản do ma trận tự tạo: mạch bị cắt cụt, tên đơn vị chỉ khác hoa/thường + khoảng trắng
    trung = _dv(subj, gr, " hình có  trục đối xứng ", "Tính đối xứng của hình phẳng tro",
                tu_ma_tran=True)
    rieng = _dv(subj, gr, "Số nguyên âm")
    db_session.add_all([goc, trung, rieng]); await db_session.flush()
    db_session.add(TopicContent(topic_id=goc.id, khai_niem="<p>ĐN</p>", trang_thai="draft"))
    await db_session.flush()

    kq = await gop_trung.tim_trung(db_session, subj.id, gr.id)
    nhom = kq["chac_chan"]
    assert len(nhom) == 1                       # chỉ 1 nhóm trùng, "Số nguyên âm" không bị gom
    assert nhom[0]["giu"]["id"] == goc.id       # giữ bản CÓ nội dung
    assert [b["id"] for b in nhom[0]["bo"]] == [trung.id]
    assert nhom[0]["bo"][0]["tu_ma_tran"] is True


async def test_giu_ban_co_noi_dung_du_id_lon_hon(db_session):
    """Bản gốc rỗng, bản ma trận lại có bài soạn -> phải giữ bản CÓ bài."""
    subj, gr = await _mon_khoi(db_session)
    rong = _dv(subj, gr, "Số nguyên tố")
    co_bai = _dv(subj, gr, "Số nguyên tố", tu_ma_tran=True)
    db_session.add_all([rong, co_bai]); await db_session.flush()
    db_session.add(TopicContent(topic_id=co_bai.id, khai_niem="<p>x</p>", trang_thai="published"))
    await db_session.flush()

    nhom = (await gop_trung.tim_trung(db_session, subj.id, gr.id))["chac_chan"]
    assert nhom[0]["giu"]["id"] == co_bai.id and nhom[0]["giu"]["trang_thai"] == "published"


async def test_gop_doi_o_ma_tran_va_bai_hoc_sinh_sang_ban_giu(db_session):
    subj, gr = await _mon_khoi(db_session)
    giu = _dv(subj, gr, "Phép cộng", hoc_ky="hk1")
    bo = _dv(subj, gr, "Phép cộng", tu_ma_tran=True)
    hs = User(email=f"gt-{uuid.uuid4().hex[:8]}@vd.vn", name="An", role="hoc_sinh",
              password_hash="x")
    db_session.add_all([giu, bo, hs]); await db_session.flush()
    bp = Blueprint(subject_id=subj.id, grade_id=gr.id, semester="hk1")
    db_session.add(bp); await db_session.flush()
    db_session.add_all([
        BlueprintCell(blueprint_id=bp.id, muc_do="de", nang_luc="NL", yeu_cau_can_dat="YCĐ",
                      topic_id=bo.id, dang_thuc="TN", ti_le=0.4, nhom_ti_le=1),
        QuizAttempt(user_id=hs.id, topic_id=bo.id, diem=6, tong=8, dat=True),
        TopicContent(topic_id=bo.id, khai_niem="<p>bài ở bản trùng</p>", trang_thai="draft"),
    ])
    giu_id, bo_id, hs_id = giu.id, bo.id, hs.id
    await db_session.flush()

    kq = await gop_trung.gop(db_session, giu_id, [bo_id])
    assert kq["da_doi"]["o_ma_tran"] == 1 and kq["da_doi"]["luot_lam_bai"] == 1
    assert kq["da_doi"]["don_vi_xoa"] == 1

    assert await db_session.get(CurriculumTopic, bo_id) is None          # bản trùng đã đi
    cell = await db_session.scalar(select(BlueprintCell).where(BlueprintCell.blueprint_id == bp.id))
    assert cell.topic_id == giu_id                                       # ô ma trận không mồ côi
    qa = await db_session.scalar(select(QuizAttempt).filter_by(user_id=hs_id))
    assert qa.topic_id == giu_id                                         # bài đã làm vẫn còn
    # bản giữ chưa có nội dung -> bài soạn ở bản trùng được DỜI SANG, không mất
    c = await db_session.scalar(select(TopicContent).filter_by(topic_id=giu_id))
    assert c is not None and "bản trùng" in c.khai_niem


async def test_gop_khong_de_lai_hai_ban_noi_dung(db_session):
    """Cả hai bản đều có nội dung -> giữ bản đích, bỏ bản trùng (không nhân đôi)."""
    subj, gr = await _mon_khoi(db_session)
    giu = _dv(subj, gr, "Luỹ thừa", hoc_ky="hk1")
    bo = _dv(subj, gr, "Luỹ thừa", tu_ma_tran=True)
    db_session.add_all([giu, bo]); await db_session.flush()
    db_session.add_all([
        TopicContent(topic_id=giu.id, khai_niem="<p>giữ</p>", trang_thai="published"),
        TopicContent(topic_id=bo.id, khai_niem="<p>bỏ</p>", trang_thai="draft"),
    ])
    giu_id, bo_id = giu.id, bo.id
    await db_session.flush()

    await gop_trung.gop(db_session, giu_id, [bo_id])
    n = await db_session.scalar(select(func.count()).select_from(TopicContent)
                               .where(TopicContent.topic_id.in_([giu_id, bo_id])))
    assert n == 1
    c = await db_session.scalar(select(TopicContent).filter_by(topic_id=giu_id))
    assert "giữ" in c.khai_niem


async def test_gop_khong_vi_pham_unique_tien_do(db_session):
    """Học sinh có tiến độ ở CẢ HAI bản: UNIQUE(user,topic) nên phải bỏ bản trùng."""
    subj, gr = await _mon_khoi(db_session)
    giu = _dv(subj, gr, "Ước chung")
    bo = _dv(subj, gr, "Ước chung", tu_ma_tran=True)
    hs = User(email=f"gt-{uuid.uuid4().hex[:8]}@vd.vn", name="Bình", role="hoc_sinh",
              password_hash="x")
    db_session.add_all([giu, bo, hs]); await db_session.flush()
    db_session.add_all([
        StudentProgress(user_id=hs.id, topic_id=giu.id, trang_thai="dat"),
        StudentProgress(user_id=hs.id, topic_id=bo.id, trang_thai="dang"),
    ])
    giu_id, bo_id, hs_id = giu.id, bo.id, hs.id
    await db_session.flush()

    kq = await gop_trung.gop(db_session, giu_id, [bo_id])       # không được nổ IntegrityError
    assert kq["da_doi"]["tien_do_bo"] == 1
    ds = list(await db_session.scalars(select(StudentProgress).filter_by(user_id=hs_id)))
    assert len(ds) == 1 and ds[0].topic_id == giu_id and ds[0].trang_thai == "dat"


async def test_gop_bo_qua_id_giu_lan_trong_danh_sach_bo(db_session):
    subj, gr = await _mon_khoi(db_session)
    t = _dv(subj, gr, "Tập hợp"); db_session.add(t); await db_session.flush()
    tid = t.id
    kq = await gop_trung.gop(db_session, tid, [tid])
    assert kq["bo"] == [] and await db_session.get(CurriculumTopic, tid) is not None


async def test_ten_gan_giong_chi_la_NGHI_khong_gom_chac_chan(db_session):
    """Hai bài KHÁC nhau nhưng tên gần giống -> chỉ được gợi ý, không gom sẵn.

    Dữ liệu thật: "Hình có tâm đối xứng" vs "Hình có trục đối xứng" đạt 0.878.
    Gom tự động ở mức đó là gộp mất một bài.
    """
    subj, gr = await _mon_khoi(db_session)
    a = _dv(subj, gr, "Hình có tâm đối xứng")
    b = _dv(subj, gr, "Hình có trục đối xứng")
    db_session.add_all([a, b]); await db_session.flush()

    kq = await gop_trung.tim_trung(db_session, subj.id, gr.id)
    assert kq["chac_chan"] == []                       # KHÔNG gom
    assert len(kq["nghi"]) == 1
    assert kq["nghi"][0]["kieu"] == "gan"              # không ai là tiền tố của ai
    assert kq["nghi"][0]["diem"] >= gop_trung.NGHI


async def test_ten_bi_cat_cut_duoc_danh_dau_cat_cut(db_session):
    """Tên .docx bị Word cắt cụt -> đánh dấu `cat_cut` để phân biệt với trùng hình thức."""
    subj, gr = await _mon_khoi(db_session)
    dai = _dv(subj, gr, "Tính chia hết trong tập hợp các số tự nhiên. Số nguyên tố. Ước chung")
    cut = _dv(subj, gr, "Tính chia hết trong tập hợp các số tự nhiên. Số nguyên",
              tu_ma_tran=True)
    db_session.add_all([dai, cut]); await db_session.flush()

    nghi = (await gop_trung.tim_trung(db_session, subj.id, gr.id))["nghi"]
    assert len(nghi) == 1 and nghi[0]["kieu"] == "cat_cut"
    assert nghi[0]["giu"]["id"] == dai.id               # giữ bản tên đầy đủ hơn


async def test_canh_bao_khi_ca_hai_ban_deu_co_bai(db_session):
    subj, gr = await _mon_khoi(db_session)
    a = _dv(subj, gr, "Tính chia hết trong tập hợp các số tự nhiên. Số nguyên tố. Ước chung")
    b = _dv(subj, gr, "Tính chia hết trong tập hợp các số tự nhiên. Số nguyên")
    db_session.add_all([a, b]); await db_session.flush()
    db_session.add_all([
        TopicContent(topic_id=a.id, khai_niem="<p>A</p>", trang_thai="draft"),
        TopicContent(topic_id=b.id, khai_niem="<p>B</p>", trang_thai="draft"),
    ])
    await db_session.flush()

    nghi = (await gop_trung.tim_trung(db_session, subj.id, gr.id))["nghi"]
    assert nghi[0]["canh_bao_mat_bai"] is True


async def test_liet_ke_don_vi_ma_tran_chua_co_bai_de_gop_tay(db_session):
    """Ca không ngưỡng nào bắt được: tên khác hẳn (0.63) mà cùng một bài.

    Dữ liệu thật: "Tính chia hết. Số nguyên tố. Ước chung và bội chung" (danh mục)
    và "Tính chia hết trong tập hợp các số tự nhiên. Số nguyên tố. Ước chung"
    (ma trận). Phải có đường gộp tay, không thì bản dư nằm lại vĩnh viễn.
    """
    subj, gr = await _mon_khoi(db_session)
    that = _dv(subj, gr, "Tính chia hết. Số nguyên tố. Ước chung và bội chung", hoc_ky="hk1")
    du = _dv(subj, gr, "Tính chia hết trong tập hợp các số tự nhiên. Số nguyên tố. Ước chung",
             tu_ma_tran=True)
    db_session.add_all([that, du]); await db_session.flush()
    db_session.add(TopicContent(topic_id=that.id, khai_niem="<p>bài thật</p>",
                                trang_thai="published"))
    await db_session.flush()

    kq = await gop_trung.tim_trung(db_session, subj.id, gr.id)
    assert kq["chac_chan"] == [] and kq["nghi"] == []      # dưới mọi ngưỡng
    assert [b["id"] for b in kq["chua_co_bai"]] == [du.id]
    # đích để chọn phải có bản thật, KHÔNG có bản dư (không ai gộp vào bản rỗng)
    assert that.id in [x["id"] for x in kq["dich"]]
    assert du.id not in [x["id"] for x in kq["dich"]]


async def test_don_vi_ma_tran_da_co_bai_khong_bi_coi_la_du(db_session):
    """Ma trận tạo nhưng chuyên gia đã soạn bài -> KHÔNG phải bản dư."""
    subj, gr = await _mon_khoi(db_session)
    t = _dv(subj, gr, "Xác suất thực nghiệm", tu_ma_tran=True)
    db_session.add(t); await db_session.flush()
    db_session.add(TopicContent(topic_id=t.id, khai_niem="<p>đã soạn</p>", trang_thai="draft"))
    await db_session.flush()

    kq = await gop_trung.tim_trung(db_session, subj.id, gr.id)
    assert kq["chua_co_bai"] == []
    assert t.id in [x["id"] for x in kq["dich"]]

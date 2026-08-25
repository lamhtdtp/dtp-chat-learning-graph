"""`seed --phan` phải BỔ SUNG được phần thiếu trên bài ĐÃ CÓ nội dung.

Ca dùng thật trên server: 21 bài đều đã có Kiến thức + Minh hoạ + Ví dụ (3/7),
chỉ thiếu 4 phần kia. Cửa lọc cũ loại mọi đơn vị đã có TopicContent nên
`--phan` chạy ra "sẽ soạn 0 đơn vị" — im lặng không làm gì.
"""
import json
import uuid

import pytest
from sqlalchemy import select

from app.db.models import CurriculumTopic, Grade, Subject, TopicContent
import app.seed_all_lessons as S


@pytest.fixture
def mon_khoi():
    return f"MonSeed-{uuid.uuid4().hex[:6]}", f"KhoiSeed-{uuid.uuid4().hex[:6]}"


async def _dung(session, mon, khoi, *, co_noi_dung: bool):
    subj = Subject(name=mon); gr = Grade(name=khoi)
    session.add_all([subj, gr]); await session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="Mạch A",
                        don_vi_kien_thuc="Bài A", order_index=0)
    session.add(t); await session.flush()
    if co_noi_dung:
        session.add(TopicContent(
            topic_id=t.id, khai_niem="<p>chữ chuyên gia đã rà</p>",
            vi_du_json=json.dumps([{"de": "VD", "giai": "G"}]),
            minh_hoa_json=json.dumps([{"type": "image", "url": "/video/files/a.png"}]),
            quiz_json=json.dumps([{"q": "q", "o": ["a", "b"], "a": 0, "lv": "de"}]),
            trang_thai="published"))
    await session.commit()
    return t.id


def _mock(mocker, phan_html="<p>phần mới</p>"):
    return {
        "ingest": mocker.patch.object(S.ingest_svc, "ingest_draft", mocker.AsyncMock(
            return_value={"khai_niem": "<p>MỚI</p>", "vi_du": [], "anh": [],
                          "video": None, "mon": "toan"})),
        "quiz": mocker.patch.object(S.quiz_svc, "generate_quiz",
                                    mocker.AsyncMock(return_value=[])),
        "phan": mocker.patch.object(S.ingest_svc, "soan_phan",
                                    mocker.AsyncMock(return_value=phan_html)),
        "media": mocker.patch.object(S, "_sinh_media",
                                     mocker.AsyncMock(return_value=([], []))),
        "goi_y": mocker.patch.object(S.ingest_svc, "goi_y_media", mocker.AsyncMock(
            return_value={"anh": [], "video": None})),
    }


async def test_phan_bo_sung_bai_da_co_chu_va_KHONG_goi_tang_manh(
        db_session, mon_khoi, mocker):
    mon, khoi = mon_khoi
    tid = await _dung(db_session, mon, khoi, co_noi_dung=True)
    m = _mock(mocker)
    mocker.patch.object(S, "async_session_factory", lambda: _Bao(db_session))

    await S.seed(mon=mon, khoi=khoi, publish=False, force=False, media=False, phan=True)

    c = await db_session.scalar(select(TopicContent).filter_by(topic_id=tid))
    # 4 phần được thêm
    assert c.khoi_dong and c.hoat_dong and c.luyen_tap and c.bai_tap
    # chữ cũ KHÔNG bị ghi đè, và KHÔNG gọi tầng mạnh cho thứ đã có
    assert "chuyên gia đã rà" in c.khai_niem
    assert m["ingest"].await_count == 0
    assert m["quiz"].await_count == 0
    assert m["phan"].await_count == 4


async def test_khong_co_co_thi_khong_lam_gi_voi_bai_da_co(db_session, mon_khoi, mocker):
    """`seed` trần trên bài đã có nội dung: vẫn phải bỏ qua (idempotent như trước)."""
    mon, khoi = mon_khoi
    tid = await _dung(db_session, mon, khoi, co_noi_dung=True)
    m = _mock(mocker)
    mocker.patch.object(S, "async_session_factory", lambda: _Bao(db_session))

    await S.seed(mon=mon, khoi=khoi, publish=False, force=False, media=False, phan=False)

    c = await db_session.scalar(select(TopicContent).filter_by(topic_id=tid))
    assert not (c.khoi_dong or "").strip()
    assert m["ingest"].await_count == 0 and m["phan"].await_count == 0


async def test_bai_chua_co_gi_thi_soan_ca_chu_lan_phan(db_session, mon_khoi, mocker):
    mon, khoi = mon_khoi
    tid = await _dung(db_session, mon, khoi, co_noi_dung=False)
    m = _mock(mocker)
    mocker.patch.object(S, "async_session_factory", lambda: _Bao(db_session))

    await S.seed(mon=mon, khoi=khoi, publish=False, force=False, media=False, phan=True)

    c = await db_session.scalar(select(TopicContent).filter_by(topic_id=tid))
    assert "MỚI" in c.khai_niem and c.bai_tap
    assert m["ingest"].await_count == 1 and m["phan"].await_count == 4


async def test_media_bo_sung_chi_goi_tang_re(db_session, mon_khoi, mocker):
    """Bài đã có chữ, thiếu minh hoạ -> chỉ gọi goi_y_media (rẻ), không ingest_draft."""
    mon, khoi = mon_khoi
    subj = Subject(name=mon); gr = Grade(name=khoi)
    db_session.add_all([subj, gr]); await db_session.flush()
    t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="M",
                        don_vi_kien_thuc="B", order_index=0)
    db_session.add(t); await db_session.flush()
    db_session.add(TopicContent(topic_id=t.id, khai_niem="<p>đã có</p>",
                                minh_hoa_json="[]", trang_thai="published"))
    await db_session.commit()
    m = _mock(mocker)
    mocker.patch.object(S, "async_session_factory", lambda: _Bao(db_session))

    await S.seed(mon=mon, khoi=khoi, publish=False, force=False, media=True, phan=False)

    assert m["ingest"].await_count == 0
    assert m["goi_y"].await_count == 1
    assert m["media"].await_count == 1


class _Bao:
    """Bọc session của test cho `async with async_session_factory() as s`."""

    def __init__(self, s):
        self.s = s

    async def __aenter__(self):
        return self.s

    async def __aexit__(self, *a):
        return False


async def _ba_bai(session, mon, khoi):
    subj = Subject(name=mon); gr = Grade(name=khoi)
    session.add_all([subj, gr]); await session.flush()
    ids = []
    for i in range(3):
        t = CurriculumTopic(subject_id=subj.id, grade_id=gr.id, mach_noi_dung="M",
                            don_vi_kien_thuc=f"Bài {i}", order_index=i)
        session.add(t); await session.flush()
        session.add(TopicContent(topic_id=t.id, khai_niem=f"<p>cũ {i}</p>",
                                 minh_hoa_json="[]", trang_thai="published"))
        ids.append(t.id)
    await session.commit()
    return ids


async def test_chia_lo_force_khong_lam_lai_lo_truoc(db_session, mon_khoi, mocker):
    """--force làm lại MỌI bài nên phải chia lô được, không thì nhiều ngày lặp lô đầu mãi."""
    mon, khoi = mon_khoi
    ids = await _ba_bai(db_session, mon, khoi)
    m = _mock(mocker)
    mocker.patch.object(S, "async_session_factory", lambda: _Bao(db_session))

    # Lô 1: chỉ bài đầu
    await S.seed(mon=mon, khoi=khoi, publish=False, force=True, media=False,
                 phan=False, gioi_han=1)
    assert m["ingest"].await_count == 1

    # Lô 2: bỏ 1, làm 2 bài còn lại — KHÔNG chạm lại bài đầu
    await S.seed(mon=mon, khoi=khoi, publish=False, force=True, media=False,
                 phan=False, bo_qua=1, gioi_han=2)
    assert m["ingest"].await_count == 3
    goi = [c.kwargs.get("topic_id", c.args[1] if len(c.args) > 1 else None)
           for c in m["ingest"].await_args_list]
    assert goi == ids, "phải theo đúng order_index, mỗi bài đúng một lần"


async def test_khong_force_thi_khong_can_chia_lo(db_session, mon_khoi, mocker):
    """Lượt sau tự bỏ qua bài đã có -> chạy lại nhiều ngày vẫn tiến lên."""
    mon, khoi = mon_khoi
    await _ba_bai(db_session, mon, khoi)
    m = _mock(mocker)
    mocker.patch.object(S, "async_session_factory", lambda: _Bao(db_session))

    await S.seed(mon=mon, khoi=khoi, publish=False, force=False, media=False, phan=True)
    assert m["phan"].await_count == 12          # 3 bài × 4 phần
    # lượt hai: 4 phần đã có -> không còn việc gì
    await S.seed(mon=mon, khoi=khoi, publish=False, force=False, media=False, phan=True)
    assert m["phan"].await_count == 12

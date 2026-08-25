"""Tìm và gộp ĐƠN VỊ KIẾN THỨC trùng trong danh mục (REQ §2.3).

Vì sao cần: nạp ma trận .docx từng so tên bằng chuỗi tuyệt đối, nên tên lệch một
khoảng trắng ("Các hình phẳngtrong thực tiễn") hay mạch bị cắt cụt là tạo thêm
một đơn vị mới. Danh mục Toán 6 phình từ 21 lên 42 đơn vị: học sinh bấm vào bản
rỗng và thấy "đang được biên soạn" trong khi bài đã soạn nằm ở bản kia.

`matrix_loader` đã khớp gần đúng nên không đẻ thêm nữa; module này dọn phần đã
lỡ tạo. Gộp chứ không xoá thẳng: bản trùng có thể đang được ma trận trỏ vào hoặc
đã có học sinh làm bài.
"""
import logging
from collections import defaultdict

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (BlueprintCell, CurriculumTopic, QuizAttempt,
                           StudentProgress, StudySession, TopicContent)
from app.exam import diem_khop

log = logging.getLogger(__name__)

# Thứ tự ưu tiên trạng thái nội dung khi chọn bản GIỮ.
_UU_TIEN = {"published": 3, "review": 2, "draft": 1}


def _diem_giu(t: CurriculumTopic, c: TopicContent | None) -> tuple:
    """Điểm để chọn bản GIỮ. Càng lớn càng được giữ.

    Nội dung đã soạn là tiêu chí số một — gộp mà mất bài soạn thì tệ hơn để trùng.
    Sau đó ưu tiên bản KHÔNG do ma trận tự tạo (tên sạch, có học kỳ), rồi id nhỏ
    (bản gốc) để kết quả ổn định giữa các lần chạy.
    """
    return (
        _UU_TIEN.get(c.trang_thai, 0) if c else 0,
        1 if (c and (c.khai_niem or c.vi_du_json)) else 0,
        0 if t.tu_ma_tran else 1,
        1 if t.hoc_ky else 0,
        -t.id,
    )


# Ngưỡng NGHI trùng. Chỉ để GỢI Ý cho người soạn xác nhận, không bao giờ tự gộp:
# trong dữ liệu thật "Hình có tâm đối xứng" và "Hình có trục đối xứng" đạt 0.878,
# "Số nguyên âm và tập hợp…" với "Số tự nhiên và tập hợp…" đạt 0.816 — hai bài
# HOÀN TOÀN khác nhau. Không có ngưỡng nào tách được chúng khỏi ca trùng thật.
NGHI = 0.75
_DAI_TOI_THIEU = 20     # tên quá ngắn thì quan hệ tiền tố không nói được gì


async def tim_trung(session: AsyncSession, subject_id: int, grade_id: int) -> dict:
    """Đơn vị trùng trong một môn/khối, chia HAI MỨC.

    `chac_chan`: tên đơn vị giống nhau sau chuẩn hoá (chỉ khác hoa/thường, khoảng
    trắng, dấu câu cuối) — gộp hàng loạt được.

    `nghi`: từng CẶP tên gần giống, kèm điểm và kiểu. Trả cặp chứ không gom nhóm:
    gom nhóm sẽ bắc cầu "tâm đối xứng" sang "trục đối xứng" qua một tên trung
    gian rồi gộp mất bài. Mỗi cặp người soạn phải tự xác nhận.

    Chỉ so `don_vi_kien_thuc`: mạch lấy từ Word hay bị cắt cụt nên không dùng làm
    tiêu chí gộp được — cùng tên đơn vị trong cùng môn/khối là cùng một bài.
    """
    topics = list((await session.scalars(select(CurriculumTopic).filter_by(
        subject_id=subject_id, grade_id=grade_id))).all())
    if not topics:
        return []
    noi_dung = {c.topic_id: c for c in (await session.scalars(
        select(TopicContent).where(TopicContent.topic_id.in_([t.id for t in topics])))).all()}

    nhom: dict[str, list[CurriculumTopic]] = defaultdict(list)
    for t in topics:
        nhom[diem_khop.chuan(t.don_vi_kien_thuc)].append(t)

    chac_chan, dai_dien = [], []
    for ds in nhom.values():
        ds.sort(key=lambda t: _diem_giu(t, noi_dung.get(t.id)), reverse=True)
        dai_dien.append(ds[0])          # so tên gần giống trên BẢN GIỮ của mỗi nhóm
        if len(ds) > 1:
            chac_chan.append({
                "giu": _mo_ta(ds[0], noi_dung.get(ds[0].id)),
                "bo": [_mo_ta(t, noi_dung.get(t.id)) for t in ds[1:]],
            })
    chac_chan.sort(key=lambda g: g["giu"]["don_vi_kien_thuc"])

    nghi = []
    for i in range(len(dai_dien)):
        for j in range(i + 1, len(dai_dien)):
            a, b = dai_dien[i], dai_dien[j]
            d = diem_khop._giong(a.don_vi_kien_thuc, b.don_vi_kien_thuc)
            if d < NGHI:
                continue
            ca, cb = diem_khop.chuan(a.don_vi_kien_thuc), diem_khop.chuan(b.don_vi_kien_thuc)
            # Tên này là bản CẮT CỤT của tên kia -> gần như chắc chắn cùng bài.
            # Đây là dấu hiệu tách được ca trùng thật khỏi cặp "tâm/trục đối xứng"
            # (điểm cao nhưng không ai là tiền tố của ai).
            cat_cut = (min(len(ca), len(cb)) >= _DAI_TOI_THIEU
                       and (ca.startswith(cb) or cb.startswith(ca)))
            x, y = ((a, b) if _diem_giu(a, noi_dung.get(a.id))
                    >= _diem_giu(b, noi_dung.get(b.id)) else (b, a))
            nghi.append({
                "giu": _mo_ta(x, noi_dung.get(x.id)),
                "bo": [_mo_ta(y, noi_dung.get(y.id))],
                "diem": round(d, 3),
                "kieu": "cat_cut" if cat_cut else "gan",
                # Cả hai bên đều có bài -> gộp sẽ BỎ một bài, phải nói trước.
                "canh_bao_mat_bai": bool(
                    (noi_dung.get(x.id) and noi_dung[x.id].khai_niem)
                    and (noi_dung.get(y.id) and noi_dung[y.id].khai_niem)),
            })
    nghi.sort(key=lambda g: (g["kieu"] != "cat_cut", -g["diem"]))

    # Mức BA — gộp tay. Có ca không ngưỡng nào bắt được: "Tính chia hết. Số
    # nguyên tố. Ước chung và bội chung" (danh mục) và "Tính chia hết trong tập
    # hợp các số tự nhiên. Số nguyên tố. Ước chung" (ma trận) chỉ giống 0.626 mà
    # là CÙNG một bài; hạ ngưỡng tới đó thì danh sách gợi ý toàn cặp sai. Nên
    # liệt kê thẳng các đơn vị do ma trận tạo mà chưa có bài — chúng gần như luôn
    # là bản dư — kèm danh sách đích để người soạn tự chọn.
    da_liet_ke = {g["giu"]["id"] for g in chac_chan} | {
        b["id"] for g in chac_chan for b in g["bo"]}
    da_liet_ke |= {g["giu"]["id"] for g in nghi} | {
        b["id"] for g in nghi for b in g["bo"]}
    chua_co_bai = [
        _mo_ta(t, noi_dung.get(t.id)) for t in dai_dien
        if t.tu_ma_tran and t.id not in da_liet_ke
        and not (noi_dung.get(t.id) and noi_dung[t.id].khai_niem)
    ]
    chua_co_bai.sort(key=lambda b: b["don_vi_kien_thuc"])
    dich = sorted(
        ({"id": t.id, "ten": t.don_vi_kien_thuc, "mach": t.mach_noi_dung,
          "co_noi_dung": bool(noi_dung.get(t.id) and noi_dung[t.id].khai_niem)}
         for t in dai_dien if not t.tu_ma_tran or noi_dung.get(t.id)),
        key=lambda x: x["ten"])
    return {"chac_chan": chac_chan, "nghi": nghi,
            "chua_co_bai": chua_co_bai, "dich": dich}


def _mo_ta(t: CurriculumTopic, c: TopicContent | None) -> dict:
    return {
        "id": t.id,
        "don_vi_kien_thuc": t.don_vi_kien_thuc,
        "mach_noi_dung": t.mach_noi_dung,
        "hoc_ky": t.hoc_ky,
        "tu_ma_tran": bool(t.tu_ma_tran),
        "trang_thai": c.trang_thai if c else None,
        "co_noi_dung": bool(c and (c.khai_niem or c.vi_du_json)),
    }


async def gop(session: AsyncSession, giu_id: int, bo_ids: list[int]) -> dict:
    """Dồn mọi tham chiếu của `bo_ids` về `giu_id` rồi xoá các bản bỏ.

    Không dùng ON DELETE CASCADE: xoá thẳng sẽ mất ô ma trận và bài học sinh đã
    làm trên bản trùng. Trả số bản ghi đã dời để báo lại cho người bấm.
    """
    bo_ids = [i for i in bo_ids if i != giu_id]
    if not bo_ids:
        return {"giu": giu_id, "bo": [], "da_doi": {}}
    if await session.get(CurriculumTopic, giu_id) is None:
        raise ValueError(f"Không tìm thấy đơn vị giữ lại (id={giu_id})")

    da_doi: dict[str, int] = {}

    # 1) Ô ma trận + lượt làm bài + phiên học: dời thẳng, không có ràng buộc unique.
    for ten, model in (("o_ma_tran", BlueprintCell), ("luot_lam_bai", QuizAttempt),
                       ("phien_hoc", StudySession)):
        r = await session.execute(update(model).where(model.topic_id.in_(bo_ids))
                                  .values(topic_id=giu_id))
        da_doi[ten] = r.rowcount or 0

    # 2) Tiến độ: UNIQUE(user_id, topic_id) nên học sinh đã có tiến độ ở bản giữ
    #    thì KHÔNG dời được — xoá bản trùng, giữ trạng thái ở bản giữ.
    da_co = set(await session.scalars(select(StudentProgress.user_id)
                                      .where(StudentProgress.topic_id == giu_id)))
    r = await session.execute(delete(StudentProgress).where(
        StudentProgress.topic_id.in_(bo_ids), StudentProgress.user_id.in_(da_co or {-1})))
    da_doi["tien_do_bo"] = r.rowcount or 0
    r = await session.execute(update(StudentProgress)
                              .where(StudentProgress.topic_id.in_(bo_ids))
                              .values(topic_id=giu_id))
    da_doi["tien_do_doi"] = r.rowcount or 0

    # 3) Nội dung: bản giữ đã có thì bỏ bản trùng, chưa có thì dời sang.
    giu_co = await session.scalar(select(func.count()).select_from(TopicContent)
                                 .where(TopicContent.topic_id == giu_id))
    if giu_co:
        r = await session.execute(delete(TopicContent)
                                  .where(TopicContent.topic_id.in_(bo_ids)))
        da_doi["noi_dung_bo"] = r.rowcount or 0
    else:
        cs = list((await session.scalars(select(TopicContent)
                                        .where(TopicContent.topic_id.in_(bo_ids)))).all())
        cs.sort(key=lambda c: _UU_TIEN.get(c.trang_thai, 0), reverse=True)
        for i, c in enumerate(cs):
            if i == 0:
                c.topic_id = giu_id
            else:
                await session.delete(c)
        da_doi["noi_dung_doi"] = 1 if cs else 0

    await session.flush()
    r = await session.execute(delete(CurriculumTopic).where(CurriculumTopic.id.in_(bo_ids)))
    da_doi["don_vi_xoa"] = r.rowcount or 0
    log.info("Gộp đơn vị trùng: giữ %s, bỏ %s -> %s", giu_id, bo_ids, da_doi)
    return {"giu": giu_id, "bo": bo_ids, "da_doi": da_doi}

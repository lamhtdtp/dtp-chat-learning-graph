"""US-25 (Luyện thêm từ kho đề) — hàm thuần chọn câu `app.lessons.luyen_them.chon_cau`.

HỢP ĐỒNG (đã chốt với người điều phối, DEV đọc trước khi code):

    chon_cau(items: list[dict], ar_ids: set[str], *, toi_da: int = 4, seed: int = 0) -> list[str]

* `items` là phần tử `items` của `GET content /pool` (testbank): mỗi phần tử có ít nhất
  `qid, ar_id, family_qid, group_id` (group_id có thể None).
* Trả danh sách `qid` THEO THỨ TỰ ĐỀ.
* Chỉ lấy câu có `ar_id` thuộc `ar_ids`.
* Mỗi `family_qid` tối đa 1 câu (bản gốc và bản nhân bản không cùng xuất hiện).
* Câu cùng `group_id`: lấy TRỌN nhóm hoặc không lấy; đứng LIỀN nhau; cả nhóm tính vào
  giới hạn `toi_da` (nhóm lớn hơn phần còn lại thì bỏ cả nhóm, không cắt dở).
* Trải đều các YCCĐ: vòng qua từng YCCĐ trước khi lấy câu thứ hai của cùng một YCCĐ.
  Bài có nhiều YCCĐ hơn `toi_da` thì thứ tự/chọn YCCĐ phụ thuộc `seed` (các lượt sau phủ dần).
* Cùng `seed` + cùng đầu vào -> cùng kết quả (xác định). Không sửa `items`.
* Không ép tỉ lệ mức độ (Q4 của US). Không có câu hợp lệ -> `[]`.

Kịch bản phủ: 2, 3, 4 (phần chọn), 7 (phần lọc theo ar_ids).
"""
import random

import pytest

from app.lessons.luyen_them import chon_cau


def _it(qid, ar, *, family=None, group=None):
    return {"qid": qid, "ar_id": ar, "family_qid": family or qid, "group_id": group,
            "difficulty": "B", "format_code": "TN1"}


def _pool(spec: dict[str, int]):
    """{ar_id: số câu} -> các câu rời, mỗi câu một họ riêng."""
    return [_it(f"{ar}-q{i}", ar) for ar, n in spec.items() for i in range(n)]


def _ar_cua(items, qids):
    m = {x["qid"]: x["ar_id"] for x in items}
    return [m[q] for q in qids]


def test_chi_lay_cau_thuoc_ycd_cua_bai():
    """Câu của YCCĐ khác bài không bao giờ được lọt vào lượt luyện thêm (US-25 KB2, KB7)."""
    items = _pool({"A1": 3, "A2": 3, "KHAC": 5})
    out = chon_cau(items, {"A1", "A2"})
    assert out and set(_ar_cua(items, out)) <= {"A1", "A2"}


def test_toi_da_4_cau_mac_dinh():
    items = _pool({"A1": 5, "A2": 5})
    assert len(chon_cau(items, {"A1", "A2"})) == 4


def test_toi_da_theo_tham_so():
    items = _pool({"A1": 5, "A2": 5})
    assert len(chon_cau(items, {"A1", "A2"}, toi_da=2)) == 2


def test_kho_it_hon_toi_da_thi_lay_het_khong_bia():
    """KB4: kho có 2 câu thì trả đúng 2 câu đó, không bù."""
    items = _pool({"A1": 1, "A2": 1, "KHAC": 4})
    out = chon_cau(items, {"A1", "A2"})
    assert sorted(out) == ["A1-q0", "A2-q0"]


def test_khong_co_cau_hop_le_thi_rong():
    assert chon_cau([], {"A1"}) == []
    assert chon_cau(_pool({"KHAC": 3}), {"A1"}) == []
    assert chon_cau(_pool({"A1": 3}), set()) == []


def test_tra_ve_list_qid_khong_trung():
    items = _pool({"A1": 4, "A2": 4})
    out = chon_cau(items, {"A1", "A2"})
    assert isinstance(out, list) and all(isinstance(q, str) for q in out)
    assert len(out) == len(set(out))


def test_moi_ho_cau_toi_da_mot_cau():
    """Bản gốc và bản nhân bản của cùng một câu là một họ — làm cả hai là làm lặp."""
    items = [_it("g1", "A1", family="F1"), _it("g1-v2", "A1", family="F1"),
             _it("g1-v3", "A1", family="F1"), _it("h1", "A1", family="F2"),
             _it("k1", "A2", family="F3"), _it("k1-v2", "A2", family="F3")]
    out = chon_cau(items, {"A1", "A2"})
    fam = {x["qid"]: x["family_qid"] for x in items}
    fs = [fam[q] for q in out]
    assert len(fs) == len(set(fs))
    assert sorted(set(fs)) == ["F1", "F2", "F3"]       # đủ 3 họ, mỗi họ một đại diện


def test_ba_ycd_moi_ycd_co_it_nhat_mot_cau():
    """KB3: 3 YCCĐ, YCCĐ nào cũng ≥2 câu -> mỗi YCCĐ có mặt, kể cả khi seed khác nhau."""
    items = _pool({"A1": 3, "A2": 3, "A3": 3})
    for seed in range(30):
        out = chon_cau(items, {"A1", "A2", "A3"}, seed=seed)
        assert len(out) == 4
        assert set(_ar_cua(items, out)) == {"A1", "A2", "A3"}, seed


def test_hai_ycd_nhieu_cau_chia_deu_2_2():
    items = _pool({"A1": 6, "A2": 6})
    for seed in range(10):
        ars = _ar_cua(items, chon_cau(items, {"A1", "A2"}, seed=seed))
        assert ars.count("A1") == 2 and ars.count("A2") == 2


def test_chua_lay_cau_thu_hai_khi_con_ycd_chua_co_cau():
    """Q3: một YCCĐ có 10 câu cũng không được nuốt chỗ của YCCĐ chỉ có 1 câu."""
    items = _pool({"A1": 10, "A2": 1, "A3": 1})
    for seed in range(10):
        ars = _ar_cua(items, chon_cau(items, {"A1", "A2", "A3"}, seed=seed))
        assert {"A2", "A3"} <= set(ars) and ars.count("A1") == 2


def test_nhieu_hon_4_ycd_thi_chon_theo_seed_va_phu_dan():
    """Bài có 6 YCCĐ: mỗi lượt 4 YCCĐ khác nhau; qua nhiều seed phủ nhiều hơn 4 YCCĐ."""
    ar_ids = {f"A{i}" for i in range(6)}
    items = _pool({a: 3 for a in ar_ids})
    thay = set()
    for seed in range(40):
        ars = _ar_cua(items, chon_cau(items, ar_ids, seed=seed))
        assert len(ars) == 4 and len(set(ars)) == 4
        thay |= set(ars)
    assert len(thay) > 4


def test_cung_seed_cung_ket_qua():
    items = _pool({"A1": 5, "A2": 5, "A3": 5})
    a = chon_cau(items, {"A1", "A2", "A3"}, seed=7)
    assert chon_cau(items, {"A1", "A2", "A3"}, seed=7) == a


def test_seed_khac_cho_luot_khac_khi_kho_nhieu_cau():
    """Làm lại là rút lượt mới (KB19, Q5) — không phải lúc nào cũng ra đúng bộ cũ."""
    items = _pool({"A1": 8, "A2": 8})
    kq = {tuple(chon_cau(items, {"A1", "A2"}, seed=s)) for s in range(20)}
    assert len(kq) > 1


def test_khong_sua_danh_sach_dau_vao():
    items = _pool({"A1": 3, "A2": 3})
    truoc = [dict(x) for x in items]
    chon_cau(items, {"A1", "A2"}, seed=3)
    assert items == truoc


def _nhom(gid, ar, n):
    return [_it(f"{gid}-c{i}", ar, group=gid) for i in range(n)]


def test_nhom_du_kien_chung_lay_tron_va_dung_lien_nhau():
    """KB3: dữ kiện chung hiện một lần trước câu đầu nhóm -> các câu con phải liền nhau."""
    items = _nhom("G1", "A1", 2) + _pool({"A2": 3})
    for seed in range(30):
        out = chon_cau(items, {"A1", "A2"}, seed=seed)
        co = [q for q in out if q.startswith("G1-")]
        assert co == [] or co == ["G1-c0", "G1-c1"] or co == ["G1-c1", "G1-c0"], (seed, out)
        if co:
            i = out.index(co[0])
            assert out[i:i + 2] == co               # liền nhau
        assert len(out) <= 4


def test_nhom_tinh_ca_vao_gioi_han():
    """Nhóm 3 câu + câu lẻ: tổng không quá 4 (tính cả từng câu con)."""
    items = _nhom("G1", "A1", 3) + _pool({"A2": 5})
    for seed in range(30):
        out = chon_cau(items, {"A1", "A2"}, seed=seed)
        assert len(out) <= 4, (seed, out)


def test_nhom_lon_hon_gioi_han_thi_bo_ca_nhom_khong_cat_do():
    """Nhóm 5 câu > toi_da=4: không được lấy 4 trong 5 (dữ kiện thiếu câu là sai đề)."""
    items = _nhom("G1", "A1", 5) + _pool({"A2": 4})
    for seed in range(20):
        out = chon_cau(items, {"A1", "A2"}, seed=seed)
        assert not [q for q in out if q.startswith("G1-")], (seed, out)
        assert len(out) == 4


def test_nhom_vua_du_gioi_han_thi_lay_dung_nhom():
    items = _nhom("G1", "A1", 4)
    out = chon_cau(items, {"A1"})
    assert sorted(out) == [f"G1-c{i}" for i in range(4)]


def test_tinh_chat_tong_hop_ngau_nhien():
    """Bất biến trên nhiều bộ kho ngẫu nhiên (seed cố định để tái hiện được)."""
    rng = random.Random(2026)
    for vong in range(150):
        items, n = [], 0
        for a in range(rng.randint(1, 6)):
            for _ in range(rng.randint(0, 5)):
                n += 1
                items.append(_it(f"s{n}", f"A{a}", family=f"F{rng.randint(1, 12)}"))
        for g in range(rng.randint(0, 2)):
            ar = f"A{rng.randint(0, 5)}"
            for k in range(rng.randint(2, 4)):
                n += 1
                items.append(_it(f"s{n}", ar, family=f"GF{g}-{k}", group=f"G{g}"))
        ar_ids = {f"A{a}" for a in range(rng.randint(1, 6))}
        out = chon_cau(items, ar_ids, toi_da=4, seed=vong)
        by = {x["qid"]: x for x in items}
        assert len(out) <= 4 and len(out) == len(set(out)), (vong, out)
        assert all(by[q]["ar_id"] in ar_ids for q in out), (vong, out)
        fam = [by[q]["family_qid"] for q in out]
        assert len(fam) == len(set(fam)), (vong, out)
        for g in {by[q]["group_id"] for q in out if by[q]["group_id"]}:
            thanh_vien = [x["qid"] for x in items if x["group_id"] == g and x["ar_id"] in ar_ids]
            vi_tri = sorted(out.index(q) for q in thanh_vien if q in out)
            assert len(vi_tri) == len(thanh_vien), (vong, g, out)            # trọn nhóm
            assert vi_tri == list(range(vi_tri[0], vi_tri[0] + len(vi_tri))), (vong, g, out)  # liền
        # Đủ câu thì phải đủ 4: kho còn nhiều câu rời mà trả thiếu là lỗi chọn.
        roi = {x["family_qid"] for x in items if x["ar_id"] in ar_ids and not x["group_id"]}
        if len(roi) >= 4 and not any(x["group_id"] for x in items):
            assert len(out) == 4, (vong, out)
        assert out == chon_cau(items, ar_ids, toi_da=4, seed=vong)


@pytest.mark.parametrize("toi_da", [1, 2, 3])
def test_toi_da_nho_van_tuan_thu(toi_da):
    items = _pool({"A1": 4, "A2": 4, "A3": 4})
    assert len(chon_cau(items, {"A1", "A2", "A3"}, toi_da=toi_da)) == toi_da

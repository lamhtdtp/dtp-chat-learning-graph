from app.llm import cache


def test_key_gom_du_mon_khoi_chuong_role():
    k1 = cache.build_cache_key("qa", "Tập hợp là gì?", mon="toan", khoi="lop_6", chuong=1, role="hoc_sinh")
    # đổi bất kỳ chiều ngữ cảnh nào -> key phải khác (không trả nhầm cache khối/vai trò khác)
    assert k1 != cache.build_cache_key("qa", "Tập hợp là gì?", mon="toan", khoi="lop_7", chuong=1, role="hoc_sinh")
    assert k1 != cache.build_cache_key("qa", "Tập hợp là gì?", mon="toan", khoi="lop_6", chuong=2, role="hoc_sinh")
    assert k1 != cache.build_cache_key("qa", "Tập hợp là gì?", mon="toan", khoi="lop_6", chuong=1, role="giao_vien")
    assert k1 != cache.build_cache_key("qa", "Tập hợp là gì?", mon="ly", khoi="lop_6", chuong=1, role="hoc_sinh")


def test_key_chuan_hoa_cau_hoi_bat_bien_vun_vat():
    # hoa/thường, khoảng trắng thừa, dấu ? cuối -> cùng key (bắt câu gần trùng)
    base = cache.build_cache_key("qa", "Tập hợp là gì?", mon="toan", khoi="lop_6", chuong=1, role="hoc_sinh")
    assert base == cache.build_cache_key("qa", "  tập hợp   là gì  ", mon="toan", khoi="lop_6", chuong=1, role="hoc_sinh")
    assert base == cache.build_cache_key("qa", "TẬP HỢP LÀ GÌ", mon="toan", khoi="lop_6", chuong=1, role="hoc_sinh")


def test_key_on_dinh_qua_nhieu_lan_goi():
    a = cache.build_cache_key("qa", "x", mon="toan", khoi="lop_6", chuong=None, role="hoc_sinh")
    b = cache.build_cache_key("qa", "x", mon="toan", khoi="lop_6", chuong=None, role="hoc_sinh")
    assert a == b and a.startswith("llmcache:")


def test_task_khac_nhau_key_khac_nhau():
    assert cache.build_cache_key("qa", "x", mon="toan", khoi="lop_6", chuong=1, role="hoc_sinh") != \
           cache.build_cache_key("review_suggestion", "x", mon="toan", khoi="lop_6", chuong=1, role="hoc_sinh")


async def test_cache_get_set_qua_redis_gia_lap(mocker):
    store: dict[str, str] = {}
    fake = mocker.Mock()
    fake.get = mocker.AsyncMock(side_effect=lambda k: store.get(k))
    fake.set = mocker.AsyncMock(side_effect=lambda k, v, ex=None: store.__setitem__(k, v))
    mocker.patch("app.llm.cache._redis", return_value=fake)

    assert await cache.get("llmcache:abc") is None
    await cache.set("llmcache:abc", "câu trả lời")
    assert await cache.get("llmcache:abc") == "câu trả lời"

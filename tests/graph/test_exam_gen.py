import json

from app.exam.check import CauHoi
from app.graph.exam_build import MAX_LAN_LAP, build_exam_graph
from app.graph.nodes import exam_gen as node_mod


def _fake_llm_returning(cau_hoi_dicts):
    async def fake(task, messages, **kw):
        return json.dumps({"cau_hoi": cau_hoi_dicts})
    return fake


def _q(muc_do, n):
    return [{"muc_do": muc_do, "noi_dung": f"câu {i}", "dap_an": "x", "loi_giai": "y"}
            for i in range(n)]


# ----- _parse_cau_hoi: chịu được JSON bị CẮT (unterminated) không sập -----

def test_parse_cau_hoi_json_bi_cat_van_vot_duoc_cau_hoan_chinh():
    # câu 1 hoàn chỉnh, câu 2 bị cắt giữa chuỗi (LLM chạm max_tokens)
    raw = (
        '{"cau_hoi":[{"muc_do":"de","noi_dung":"1+1=?","dap_an":"2","loi_giai":"cong"},'
        '{"muc_do":"kho","noi_dung":"Giai thich dai dong chua ke'
    )
    cau = node_mod._parse_cau_hoi(raw)
    assert len(cau) == 1  # câu cắt bị bỏ, không JSONDecodeError
    assert cau[0].muc_do == "de"


def test_parse_cau_hoi_rac_tra_rong_khong_sap():
    assert node_mod._parse_cau_hoi("xin lỗi tôi không trả lời được") == []


def test_parse_cau_hoi_fenced_json():
    raw = '```json\n{"cau_hoi":[{"muc_do":"de","noi_dung":"x","dap_an":"y","loi_giai":"z"}]}\n```'
    assert len(node_mod._parse_cau_hoi(raw)) == 1


def test_system_prompt_theo_mon():
    assert "Tiếng Anh" in node_mod._system("tieng_anh")
    assert "Tiếng Anh" not in node_mod._system("toan")


# ----- exam_gen_node: hợp đồng, chỉ sinh phần thiếu -----

async def test_exam_gen_node_sinh_dung_json_va_tang_so_lan_lap(mocker):
    mocker.patch("app.graph.nodes.exam_gen.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.graph.nodes.exam_gen.gateway.complete",
                 side_effect=_fake_llm_returning(_q("de", 2) + _q("kho", 1)))

    out = await node_mod.exam_gen_node({
        "mach_noi_dung": "Số tự nhiên", "chi_tieu": {"de": 2, "kho": 1},
        "de_thi": [], "so_lan_lap": 0,
    })

    assert len(out["de_thi"]) == 3
    assert out["so_lan_lap"] == 1


async def test_exam_gen_node_dung_task_exam_gen(mocker):
    mocker.patch("app.graph.nodes.exam_gen.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    spy = mocker.patch("app.graph.nodes.exam_gen.gateway.complete",
                       side_effect=_fake_llm_returning(_q("de", 1)))

    await node_mod.exam_gen_node({"mach_noi_dung": "x", "chi_tieu": {"de": 1},
                                  "de_thi": [], "so_lan_lap": 0})

    assert spy.call_args.kwargs["task"] == "exam_gen"


async def test_exam_gen_node_khong_lam_gi_khi_da_du(mocker):
    llm = mocker.patch("app.graph.nodes.exam_gen.gateway.complete", mocker.AsyncMock())
    out = await node_mod.exam_gen_node({
        "mach_noi_dung": "x", "chi_tieu": {"de": 1},
        "de_thi": [CauHoi(muc_do="de")], "so_lan_lap": 0,
    })
    assert out == {}
    llm.assert_not_awaited()


# ----- loop graph -----

async def test_exam_graph_dung_khi_du_ngay_lan_dau(mocker):
    mocker.patch("app.graph.nodes.exam_gen.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    mocker.patch("app.graph.nodes.exam_gen.gateway.complete",
                 side_effect=_fake_llm_returning(_q("de", 2) + _q("kho", 1)))

    app = build_exam_graph()
    out = await app.ainvoke({"mach_noi_dung": "Số tự nhiên", "chi_tieu": {"de": 2, "kho": 1},
                             "de_thi": [], "so_lan_lap": 0})

    assert out["so_lan_lap"] == 1
    assert out.get("canh_bao") is None
    assert len(out["de_thi"]) == 3


async def test_exam_graph_sinh_bu_phan_thieu_qua_nhieu_vong(mocker):
    mocker.patch("app.graph.nodes.exam_gen.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    # lần 1 chỉ sinh 1/2 câu dễ; lần 2 sinh nốt phần thiếu
    calls = [_q("de", 1), _q("de", 1)]

    async def fake(task, messages, **kw):
        return json.dumps({"cau_hoi": calls.pop(0)})
    mocker.patch("app.graph.nodes.exam_gen.gateway.complete", side_effect=fake)

    app = build_exam_graph()
    out = await app.ainvoke({"mach_noi_dung": "x", "chi_tieu": {"de": 2},
                             "de_thi": [], "so_lan_lap": 0})

    assert len(out["de_thi"]) == 2
    assert out["so_lan_lap"] == 2
    assert out.get("canh_bao") is None


async def test_exam_graph_cham_tran_khong_lap_vo_han(mocker):
    mocker.patch("app.graph.nodes.exam_gen.retriever.retrieve", mocker.AsyncMock(return_value=[]))
    # LLM "lì": mỗi vòng chỉ sinh 1 câu dễ, không bao giờ đủ 5 -> phải dừng ở trần
    mocker.patch("app.graph.nodes.exam_gen.gateway.complete",
                 side_effect=_fake_llm_returning(_q("de", 1)))

    app = build_exam_graph()
    out = await app.ainvoke({"mach_noi_dung": "x", "chi_tieu": {"de": 5},
                             "de_thi": [], "so_lan_lap": 0})

    assert out["so_lan_lap"] == MAX_LAN_LAP  # dừng đúng ở trần, không lặp mãi
    assert out["canh_bao"] is not None and "thiếu" in out["canh_bao"]

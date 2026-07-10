from app.video import script as script_mod
from app.video.guard import check_script
from app.video.script import Slide, Storyboard, generate_script


def _sb(*formulas: str) -> Storyboard:
    return Storyboard(tieu_de="t", slides=[
        Slide(tieu_de="s", y_chinh=["ý"], cong_thuc=list(formulas), loi_thoai="lời"),
    ])


# ----- US-17 Scenario 2: kịch bản đi qua gateway -----

async def test_generate_script_goi_qua_gateway(mocker):
    fake = '{"tieu_de":"Số nguyên tố","slides":[{"tieu_de":"Định nghĩa",' \
           '"y_chinh":["chỉ có 2 ước"],"cong_thuc":[],"loi_thoai":"Số nguyên tố..."}]}'
    llm = mocker.patch("app.video.script.gateway.complete",
                       mocker.AsyncMock(return_value=fake))
    sb = await generate_script("Số nguyên tố là số chỉ có hai ước là 1 và chính nó.")
    assert llm.await_args.kwargs["task"] == "video_script"
    assert sb.slides[0].tieu_de == "Định nghĩa"


async def test_generate_script_boc_json_trong_code_fence(mocker):
    fake = '```json\n{"tieu_de":"x","slides":[{"loi_thoai":"a"}]}\n```'
    mocker.patch("app.video.script.gateway.complete", mocker.AsyncMock(return_value=fake))
    sb = await generate_script("...")
    assert sb.slides[0].loi_thoai == "a"


async def test_generate_script_dung_nap_latex_backslash_tran(mocker):
    # LLM trả LaTeX có backslash trần (\{ \in) -> JSON vỡ; _parse phải cứu được.
    fake = '{"tieu_de":"Tập hợp","slides":[{"cong_thuc":["A=\\{x \\in N\\}"],"loi_thoai":"a"}]}'
    mocker.patch("app.video.script.gateway.complete", mocker.AsyncMock(return_value=fake))
    sb = await generate_script("...")
    assert sb.slides[0].cong_thuc == ["A=\\{x \\in N\\}"]


# ----- US-17 Scenario 4: guard chặn công thức lệch -----

def test_guard_dat_khi_cong_thuc_bam_cau_tra_loi():
    answer = "Tính chất giao hoán: $a.b = b.a$. Tính chất kết hợp."
    assert check_script(_sb("a.b=b.a"), answer).ok is True


def test_guard_chan_cong_thuc_lech():
    answer = "Tính chất giao hoán của phép nhân: $a.b = b.a$."
    res = check_script(_sb("a+b=b+a"), answer)  # kịch bản bịa công thức KHÁC
    assert res.ok is False
    assert "a+b=b+a" in res.reason


def test_guard_chan_kich_ban_rong():
    assert check_script(Storyboard(slides=[]), "bất kỳ").ok is False

"""qa_node khi có NỘI DUNG BÀI ĐANG HỌC (lát 1).

Trước đây node chỉ biết SGK: retrieve rỗng là trả "không tìm thấy trong SGK" —
kể cả khi học sinh đang hỏi về đúng đoạn chữ hiện trên màn hình.
"""
from app.graph.grounding import KHONG_TIM_THAY, has_grounding
from app.graph.nodes.qa import qa_node
from app.retrieval.retriever import RetrievedChunk

_BAI = "KHÁI NIỆM:\nSố nguyên tố chỉ có hai ước."


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(content="…", score=0.9, chuong_so=1, bai_so=10, page_no=45,
                          tap=1, loai_noi_dung="ly_thuyet", nguon="Toán 6, tr.45")


def test_noi_dung_bai_la_can_cu_hop_le():
    assert has_grounding([], _BAI) is True
    assert has_grounding([], "   ") is False      # rỗng/toàn khoảng trắng thì không
    assert has_grounding([], None) is False


async def test_khong_co_sgk_nhung_co_bai_thi_van_tra_loi(mocker):
    """Đây là ca hay gặp nhất: bài do chuyên gia soạn, SGK chưa nạp trang tương ứng."""
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete",
                      mocker.AsyncMock(return_value="Vì nó chỉ có hai ước."))
    out = await qa_node({"messages": [{"role": "user", "content": "Vì sao?"}],
                         "retrieved": [], "bai_hoc": _BAI, "topic_id": 7, "anchor": "khai_niem"})
    assert KHONG_TIM_THAY not in out["answer"]
    # retrieved rỗng -> `chuong` phải là None chứ không được đọc retrieved[0]
    assert gw.call_args.kwargs["cache_ctx"]["chuong"] is None
    assert "NGỮ CẢNH BÀI ĐANG HỌC" in gw.call_args.kwargs["messages"][0]["content"]


async def test_khong_co_ca_hai_thi_khong_goi_llm(mocker):
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete", mocker.AsyncMock())
    out = await qa_node({"messages": [{"role": "user", "content": "Thời tiết?"}], "retrieved": []})
    assert KHONG_TIM_THAY in out["answer"] and gw.await_count == 0


async def test_bai_dat_truoc_sgk_trong_prompt(mocker):
    """Thứ tự trong prompt CHÍNH LÀ thứ tự ưu tiên đã dặn mô hình."""
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete", mocker.AsyncMock(return_value="ok"))
    await qa_node({"messages": [{"role": "user", "content": "?"}],
                   "retrieved": [_chunk()], "bai_hoc": _BAI})
    p = gw.call_args.kwargs["messages"][0]["content"]
    assert p.index("NGỮ CẢNH BÀI ĐANG HỌC") < p.index("NGỮ CẢNH SGK")


async def test_cache_tach_theo_bai_va_doan(mocker):
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete", mocker.AsyncMock(return_value="ok"))
    await qa_node({"messages": [{"role": "user", "content": "Giải thích lại đi"}],
                   "retrieved": [_chunk()], "bai_hoc": _BAI, "topic_id": 12, "anchor": "vi_du:2"})
    ctx = gw.call_args.kwargs["cache_ctx"]
    assert ctx["topic_id"] == 12 and ctx["anchor"] == "vi_du:2"


# ─── Phạm vi CẢ CUỐN vẫn phải biết em ấy đang mở bài nào ─────────────────────

async def test_ca_cuon_bao_mo_hinh_biet_bai_dang_mo(mocker):
    """Chip gợi ý đặt sẵn dưới bài học nói "bài này" — mô hình phải giải được.

    Thẻ cuối bài chạy ở phạm vi `ca_cuon`, và phạm vi đó CỐ Ý không nạp nội dung
    bài (để câu trả lời không bị kéo về bài đang mở). Nhưng "không nạp nội dung"
    khác với "không biết em ấy đang đứng ở đâu": thiếu vế sau thì câu hỏi đặt sẵn
    ngay dưới tên bài lại bị hỏi ngược "em chưa nói rõ bài nào".
    """
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete",
                      mocker.AsyncMock(return_value="Em cần biết về tập hợp trước."))
    await qa_node({
        "messages": [{"role": "user", "content": "Trước khi học bài này cần biết gì?"}],
        "retrieved": [_chunk()], "bai_hoc": "", "topic_id": 7,
        "pham_vi": "ca_cuon", "muc_luc": "Số tự nhiên\n- Tập hợp",
        "bai_dang_mo": "Số tự nhiên và tập hợp các số tự nhiên",
    })

    prompt = gw.call_args.kwargs["messages"][0]["content"]
    assert "Số tự nhiên và tập hợp các số tự nhiên" in prompt
    assert "BÀI EM ẤY ĐANG MỞ" in prompt
    # Và luật phải dặn mô hình ĐỪNG hỏi lại bài nào.
    assert "bài này" in prompt


async def test_ca_cuon_van_khong_nap_noi_dung_bai(mocker):
    """Chỉ thêm TÊN bài, không được kéo theo nội dung — nếu không mất đúng tính
    chất mà phạm vi cả cuốn sinh ra để có."""
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete",
                      mocker.AsyncMock(return_value="…"))
    await qa_node({
        "messages": [{"role": "user", "content": "Toán 6 có mạch nào?"}],
        "retrieved": [_chunk()], "bai_hoc": "", "topic_id": 7,
        "pham_vi": "ca_cuon", "muc_luc": "Số tự nhiên\n- Tập hợp",
        "bai_dang_mo": "Số tự nhiên và tập hợp các số tự nhiên",
    })

    prompt = gw.call_args.kwargs["messages"][0]["content"]
    assert "NGỮ CẢNH BÀI ĐANG HỌC" not in prompt


async def test_trong_bai_khong_them_khoi_bai_dang_mo(mocker):
    """Phạm vi trong bài đã có hẳn nội dung bài; thêm một dòng tên nữa là thừa."""
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete",
                      mocker.AsyncMock(return_value="…"))
    await qa_node({
        "messages": [{"role": "user", "content": "Giải thích lại?"}],
        "retrieved": [], "bai_hoc": _BAI, "topic_id": 7, "anchor": "khai_niem",
        "bai_dang_mo": "Số nguyên tố",
    })

    assert "BÀI EM ẤY ĐANG MỞ" not in gw.call_args.kwargs["messages"][0]["content"]


async def test_cache_ctx_mang_dau_van_cua_ngu_canh(mocker):
    """Cùng câu hỏi, khác ngữ cảnh đưa cho mô hình (ở đây: khác bài đang mở) thì
    dấu vân ngữ cảnh trong cache_ctx phải khác — để gateway không trả nhầm
    câu trả lời đã cache cho ngữ cảnh cũ. Cùng ngữ cảnh thì phải GIỐNG nhau,
    không thì cache vô dụng."""
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete", mocker.AsyncMock(return_value="…"))

    async def ctx(dang_mo):
        await qa_node({
            "messages": [{"role": "user", "content": "Trước khi học bài này cần biết gì?"}],
            "retrieved": [_chunk()], "bai_hoc": "", "topic_id": 7,
            "pham_vi": "ca_cuon", "muc_luc": "Số tự nhiên\n- Tập hợp", "bai_dang_mo": dang_mo,
        })
        return gw.call_args.kwargs["cache_ctx"]["ngu_canh"]

    a, a2, b = await ctx("Tập hợp"), await ctx("Tập hợp"), await ctx("Số nguyên tố")
    assert a and a == a2 and a != b

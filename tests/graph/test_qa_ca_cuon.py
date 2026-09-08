"""qa_node ở chế độ HỎI CẢ CUỐN (`pham_vi="ca_cuon"`).

Khác chế độ trong bài ở ba điểm, và cả ba đều phải kiểm được:
  1. KHÔNG có khối "ngữ cảnh bài đang học" -> mô hình không bị dặn ưu tiên một
     bài nào, nên trả lời được câu hỏi ở chương học sinh chưa tới.
  2. CÓ khối mục lục -> câu hỏi kiểu "phần này nằm ở chương nào" mới trả lời
     được; retrieval 5-20 đoạn văn không bao giờ dựng lại được cấu trúc sách.
  3. Ngưỡng grounding vẫn nguyên: không có đoạn SGK nào thì KHÔNG gọi mô hình.
"""
from app.graph.grounding import KHONG_TIM_THAY
from app.graph.nodes.qa import qa_node
from app.retrieval.retriever import RetrievedChunk

_MUC_LUC = "Số tự nhiên\n- Tập hợp\n- Số nguyên tố\nSố nguyên\n- Số âm"


def _chunk(page: int = 45) -> RetrievedChunk:
    return RetrievedChunk(content="…", score=0.9, chuong_so=1, bai_so=10, page_no=page,
                          tap=1, loai_noi_dung="ly_thuyet", nguon=f"Toán 6, tr.{page}")


def _state(**kw) -> dict:
    return {"messages": [{"role": "user", "content": "Số nguyên tố nằm ở chương nào?"}],
            "retrieved": [_chunk()], "pham_vi": "ca_cuon", "muc_luc": _MUC_LUC, **kw}


async def test_ca_cuon_khong_dan_uu_tien_bai_nao(mocker):
    """Luật "ƯU TIÊN bài đang học" là thứ kéo câu trả lời về bài hiện tại — ở chế
    độ cả cuốn nó phải biến mất, nếu không mô hình vẫn bám một bài."""
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete", mocker.AsyncMock(return_value="ok"))
    await qa_node(_state())
    p = gw.call_args.kwargs["messages"][0]["content"]
    assert "NGỮ CẢNH BÀI ĐANG HỌC" not in p
    assert "ƯU TIÊN" not in p


async def test_ca_cuon_dua_muc_luc_vao_prompt(mocker):
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete", mocker.AsyncMock(return_value="ok"))
    await qa_node(_state())
    p = gw.call_args.kwargs["messages"][0]["content"]
    assert "MỤC LỤC CUỐN SÁCH:" in p and "Số nguyên tố" in p
    # So theo TIÊU ĐỀ KHỐI (có dấu hai chấm), không theo tên trần: phần luật cũng
    # nhắc chữ "NGỮ CẢNH SGK" nên .index("NGỮ CẢNH SGK") bắt vào câu luật.
    assert p.index("MỤC LỤC CUỐN SÁCH:") < p.index("NGỮ CẢNH SGK:")
    # Mục lục là bản đồ, không phải ngữ liệu — luật phải nói rõ để mô hình không
    # lấy tên đơn vị làm căn cứ kiến thức rồi bịa nội dung quanh nó.
    assert "BẢN ĐỒ" in p


async def test_ca_cuon_bo_qua_bai_hoc_du_co_truyen(mocker):
    """Endpoint không nên gửi `bai_hoc` ở chế độ này, nhưng node phải tự bảo vệ:
    lỡ gửi thì vẫn không được chèn vào prompt, không thì chế độ mất tác dụng."""
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete", mocker.AsyncMock(return_value="ok"))
    await qa_node(_state(bai_hoc="KHÁI NIỆM:\nSố nguyên tố chỉ có hai ước."))
    assert "NGỮ CẢNH BÀI ĐANG HỌC" not in gw.call_args.kwargs["messages"][0]["content"]


async def test_ca_cuon_khong_co_sgk_thi_khong_goi_llm(mocker):
    """Mục lục KHÔNG phải căn cứ kiến thức: chỉ có tên các bài mà trả lời nội
    dung thì đúng là bịa. Không đoạn SGK nào -> từ chối, không tốn tiền."""
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete", mocker.AsyncMock())
    out = await qa_node(_state(retrieved=[]))
    assert KHONG_TIM_THAY in out["answer"] and gw.await_count == 0


async def test_ca_cuon_vao_khoa_cache(mocker):
    """Cùng câu hỏi ở hai chế độ được trả lời bằng hai khối ngữ cảnh khác nhau."""
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete", mocker.AsyncMock(return_value="ok"))
    await qa_node(_state())
    assert gw.call_args.kwargs["cache_ctx"]["pham_vi"] == "ca_cuon"


async def test_mac_dinh_van_la_che_do_trong_bai(mocker):
    """Thiếu `pham_vi` -> giữ nguyên hành vi cũ (client chưa cập nhật)."""
    gw = mocker.patch("app.graph.nodes.qa.gateway.complete", mocker.AsyncMock(return_value="ok"))
    await qa_node({"messages": [{"role": "user", "content": "?"}], "retrieved": [_chunk()],
                   "bai_hoc": "KHÁI NIỆM:\nx"})
    p = gw.call_args.kwargs["messages"][0]["content"]
    assert "NGỮ CẢNH BÀI ĐANG HỌC" in p and "ƯU TIÊN" in p

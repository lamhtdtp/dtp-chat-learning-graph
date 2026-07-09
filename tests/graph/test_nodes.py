from app.graph.grounding import KHONG_TIM_THAY, has_grounding
from app.graph.nodes.qa import qa_node
from app.graph.nodes.solve import solve_node
from app.retrieval.retriever import RetrievedChunk


def _chunk(content="Tập hợp là một nhóm các phần tử.", score=0.8, loai="ly_thuyet"):
    return RetrievedChunk(
        content=content, score=score, chuong_so=1, bai_so=1, page_no=6, tap=1,
        loai_noi_dung=loai, nguon="Toán 6, tr.6",
    )


def test_has_grounding():
    assert has_grounding([_chunk()]) is True
    assert has_grounding([]) is False


# ----- guard chống bịa (bắt buộc theo skill rag-orchestration) -----

async def test_qa_node_short_circuit_khi_khong_co_ngu_canh(mocker):
    llm = mocker.patch("app.graph.nodes.qa.gateway.complete", mocker.AsyncMock())
    state = {"messages": [{"role": "user", "content": "Tập hợp là gì?"}], "retrieved": []}

    result = await qa_node(state)

    assert KHONG_TIM_THAY in result["answer"]
    llm.assert_not_awaited()  # KHÔNG gọi LLM khi không có ngữ cảnh


async def test_solve_node_short_circuit_khi_khong_co_ngu_canh(mocker):
    llm = mocker.patch("app.graph.nodes.solve.gateway.complete", mocker.AsyncMock())
    state = {"messages": [{"role": "user", "content": "Giải bài 2+2"}], "retrieved": []}

    result = await solve_node(state)

    assert KHONG_TIM_THAY in result["answer"]
    llm.assert_not_awaited()


# ----- hợp đồng khi CÓ ngữ cảnh (mock LLM) -----

async def test_qa_node_goi_llm_khi_co_ngu_canh(mocker):
    llm = mocker.patch("app.graph.nodes.qa.gateway.complete",
                       mocker.AsyncMock(return_value="Tập hợp là một nhóm các phần tử."))
    state = {"messages": [{"role": "user", "content": "Tập hợp là gì?"}],
             "retrieved": [_chunk()]}

    result = await qa_node(state)

    assert result["answer"] == "Tập hợp là một nhóm các phần tử."
    assert llm.await_args.kwargs["task"] == "qa"
    # ngữ cảnh retrieve được truyền vào prompt
    sent = llm.await_args.args[1] if llm.await_args.args else llm.await_args.kwargs["messages"]
    assert any("phần tử" in str(m.get("content", "")) for m in sent)


async def test_solve_node_dung_task_solve(mocker):
    llm = mocker.patch("app.graph.nodes.solve.gateway.complete",
                       mocker.AsyncMock(return_value="Bước 1... Bước 2..."))
    state = {"messages": [{"role": "user", "content": "Giải bài"}],
             "retrieved": [_chunk(loai="vi_du")]}

    result = await solve_node(state)

    assert result["answer"] == "Bước 1... Bước 2..."
    assert llm.await_args.kwargs["task"] == "solve"

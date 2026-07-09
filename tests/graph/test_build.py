from langgraph.checkpoint.memory import MemorySaver

from app.graph.build import build_graph
from app.retrieval.retriever import RetrievedChunk


def _chunk(content="Tập hợp gồm các phần tử."):
    return RetrievedChunk(content=content, score=0.8, chuong_so=1, bai_so=1,
                          page_no=6, tap=1, loai_noi_dung="ly_thuyet", nguon="tr.6")


def _patch_gateway_by_task(mocker, answers):
    """Patch gateway.complete MỘT LẦN (router/qa/solve dùng chung cùng đối
    tượng gateway.complete — patch nhiều lần sẽ đè lẫn nhau). Trả lời theo task."""
    async def fake(task, messages, **kw):
        return answers.get(task, "")
    return mocker.patch("app.llm.gateway.complete", side_effect=fake)


async def test_graph_hoi_dap_di_qua_qa_node(mocker):
    _patch_gateway_by_task(mocker, {"qa": "Tập hợp là...", "solve": "KHÔNG NÊN GỌI"})
    mocker.patch("app.graph.nodes.retrieve.retriever.retrieve",
                 mocker.AsyncMock(return_value=[_chunk()]))

    app = build_graph(checkpointer=MemorySaver())
    out = await app.ainvoke(
        {"messages": [{"role": "user", "content": "Tập hợp là gì?"}], "role": "hoc_sinh"},
        config={"configurable": {"thread_id": "t1"}},
    )

    assert out["intent"] == "hoi_dap"
    assert out["answer"] == "Tập hợp là..."


async def test_graph_giai_bai_di_qua_solve_node(mocker):
    _patch_gateway_by_task(mocker, {"qa": "KHÔNG NÊN GỌI", "solve": "Bước 1..."})
    mocker.patch("app.graph.nodes.retrieve.retriever.retrieve",
                 mocker.AsyncMock(return_value=[_chunk()]))

    app = build_graph(checkpointer=MemorySaver())
    out = await app.ainvoke(
        {"messages": [{"role": "user", "content": "Tính 2 + 3 x 5"}], "role": "hoc_sinh"},
        config={"configurable": {"thread_id": "t2"}},
    )

    assert out["intent"] == "giai_bai"
    assert out["answer"] == "Bước 1..."


async def test_graph_guard_chong_bia_khi_retrieval_rong(mocker):
    fake = _patch_gateway_by_task(mocker, {"qa": "KHÔNG NÊN GỌI"})
    mocker.patch("app.graph.nodes.retrieve.retriever.retrieve",
                 mocker.AsyncMock(return_value=[]))  # không tìm thấy

    app = build_graph(checkpointer=MemorySaver())
    out = await app.ainvoke(
        {"messages": [{"role": "user", "content": "Tập hợp là gì?"}], "role": "hoc_sinh"},
        config={"configurable": {"thread_id": "t3"}},
    )

    assert "không tìm thấy" in out["answer"].lower()
    # guard chặn LLM: gateway.complete không bị gọi với task qa/solve
    called_tasks = [c.kwargs.get("task", c.args[0] if c.args else None) for c in fake.call_args_list]
    assert "qa" not in called_tasks and "solve" not in called_tasks

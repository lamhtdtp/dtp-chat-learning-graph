"""Ghép graph phục vụ chat + gắn checkpointer Redis (stateless, resume được).

Luồng: router -> retrieve -> {qa | solve} theo intent. Đây vẫn là graph khá
tuyến tính, nhưng dùng LangGraph để có checkpointer Redis (state hội thoại qua
Redis, không giữ RAM process — điều kiện scale ngang). Node sinh_de có vòng
lặp thật sẽ thêm ở feature/exam-generation.
"""

from contextlib import asynccontextmanager

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.graph.nodes.on_tap import on_tap_node
from app.graph.nodes.qa import qa_node
from app.graph.nodes.retrieve import retrieve_node
from app.graph.nodes.solve import solve_node
from app.graph.router import router_node
from app.graph.state import ChatState


def _route_by_intent(state: ChatState) -> str:
    intent = state.get("intent")
    if intent == "giai_bai":
        return "solve"
    if intent == "on_tap":
        return "on_tap"
    return "qa"


def build_graph(checkpointer=None):
    """`checkpointer` injectable: test truyền MemorySaver, production truyền
    AsyncRedisSaver (xem build_graph_with_redis)."""
    graph = StateGraph(ChatState)
    graph.add_node("router", router_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("qa", qa_node)
    graph.add_node("solve", solve_node)
    graph.add_node("on_tap", on_tap_node)

    graph.add_edge(START, "router")
    graph.add_edge("router", "retrieve")
    graph.add_conditional_edges(
        "retrieve", _route_by_intent, {"qa": "qa", "solve": "solve", "on_tap": "on_tap"}
    )
    graph.add_edge("qa", END)
    graph.add_edge("solve", END)
    graph.add_edge("on_tap", END)

    return graph.compile(checkpointer=checkpointer)


@asynccontextmanager
async def build_graph_with_redis():
    """Graph production với checkpointer Redis (state hội thoại qua Redis, không
    RAM process). Dùng như async context manager để đóng kết nối gọn gàng."""
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver

    async with AsyncRedisSaver.from_conn_string(settings.redis_url) as saver:
        await saver.asetup()
        yield build_graph(checkpointer=saver)

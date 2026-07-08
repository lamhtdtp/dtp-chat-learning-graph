"""Graph sinh đề có VÒNG LẶP thật (khác chat graph tuyến tính): exam_gen ->
check -> nếu thiếu quay lại exam_gen (sinh bù), nếu khớp hoặc chạm trần thì
dừng. Đây là ca điển hình cần LangGraph (trạng thái tích luỹ qua nhiều lần thử).

Chặn lặp vô hạn: trần MAX_LAN_LAP — chạm trần thì dừng và trả đề tốt nhất hiện
có kèm cảnh báo, KHÔNG lặp mãi hay crash (xem skill exam-generation).
"""

from langgraph.graph import END, START, StateGraph

from app.exam.check import DeThi, kiem_tra_ti_le, tinh_phan_thieu
from app.graph.exam_state import ExamState
from app.graph.nodes.exam_gen import exam_gen_node

MAX_LAN_LAP = 3


def _check_node(state: ExamState) -> dict:
    de = DeThi(cau_hoi=list(state.get("de_thi", [])))
    if kiem_tra_ti_le(de, state["chi_tieu"]):
        return {"canh_bao": None}
    if state.get("so_lan_lap", 0) >= MAX_LAN_LAP:
        thieu = tinh_phan_thieu(de, state["chi_tieu"])
        return {"canh_bao": f"Chạm trần {MAX_LAN_LAP} lần sinh, vẫn thiếu: {thieu}"}
    return {}


def _tiep_tuc_hay_dung(state: ExamState) -> str:
    de = DeThi(cau_hoi=list(state.get("de_thi", [])))
    if kiem_tra_ti_le(de, state["chi_tieu"]):
        return "dung"
    if state.get("so_lan_lap", 0) >= MAX_LAN_LAP:
        return "dung"  # best-effort, tránh lặp vô hạn
    return "tiep_tuc"


def build_exam_graph():
    graph = StateGraph(ExamState)
    graph.add_node("exam_gen", exam_gen_node)
    graph.add_node("check", _check_node)

    graph.add_edge(START, "exam_gen")
    graph.add_edge("exam_gen", "check")
    graph.add_conditional_edges(
        "check", _tiep_tuc_hay_dung, {"tiep_tuc": "exam_gen", "dung": END}
    )
    return graph.compile()

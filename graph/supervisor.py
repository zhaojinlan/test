"""
LangGraph Supervisor 条件监督图
外层 ReAct：Supervisor Thought → 子代理 Action → 状态 Observation → 循环
"""

from langgraph.graph import StateGraph, END
from graph.state import SupervisorState
from graph.nodes import (
    analyze_question,
    decompose_question,
    supervisor_decide,
    research_execute,
    analysis_execute,
    verify_execute,
    synthesize,
    format_answer,
)


def _route_after_supervisor(state: SupervisorState) -> str:
    """根据 Supervisor 的 next_action 路由到对应节点"""
    action = state.get("next_action", "").upper()
    route_map = {
        "RESEARCH": "research_execute",
        "ANALYZE": "analysis_execute",
        "VERIFY": "verify_execute",
        "SYNTHESIZE": "synthesize",
    }
    return route_map.get(action, "synthesize")


def build_supervisor_graph() -> StateGraph:
    """
    构建并编译 Supervisor 条件监督图。

    图结构:
        START
          → analyze_question
          → decompose_question
          → supervisor_decide  ←──────────────────┐
          → (conditional)                          │
              ├─ RESEARCH  → research_execute  ────┤
              ├─ ANALYZE   → analysis_execute  ────┤
              ├─ VERIFY    → verify_execute    ────┘
              └─ SYNTHESIZE → synthesize
                              → format_answer
                              → END
    """
    workflow = StateGraph(SupervisorState)

    # ---- 添加节点 ----
    workflow.add_node("analyze_question", analyze_question)
    workflow.add_node("decompose_question", decompose_question)
    workflow.add_node("supervisor_decide", supervisor_decide)
    workflow.add_node("research_execute", research_execute)
    workflow.add_node("analysis_execute", analysis_execute)
    workflow.add_node("verify_execute", verify_execute)
    workflow.add_node("synthesize", synthesize)
    workflow.add_node("format_answer", format_answer)

    # ---- 线性边 ----
    workflow.set_entry_point("analyze_question")
    workflow.add_edge("analyze_question", "decompose_question")
    workflow.add_edge("decompose_question", "supervisor_decide")

    # ---- 条件边：Supervisor 路由 ----
    workflow.add_conditional_edges(
        "supervisor_decide",
        _route_after_supervisor,
        {
            "research_execute": "research_execute",
            "analysis_execute": "analysis_execute",
            "verify_execute": "verify_execute",
            "synthesize": "synthesize",
        },
    )

    # ---- 子代理执行完毕 → 回到 Supervisor（形成循环）----
    workflow.add_edge("research_execute", "supervisor_decide")
    workflow.add_edge("analysis_execute", "supervisor_decide")
    workflow.add_edge("verify_execute", "supervisor_decide")

    # ---- 综合 → 格式化 → 结束 ----
    workflow.add_edge("synthesize", "format_answer")
    workflow.add_edge("format_answer", END)

    return workflow.compile()

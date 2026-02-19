"""
LangGraph 线性流水线
预处理 → GroupChat 多智能体协作 → 后处理
"""

from langgraph.graph import StateGraph, END
from graph.state import SupervisorState
from graph.nodes import (
    analyze_question,
    decompose_question,
    group_chat_execute,
    synthesize,
    format_answer,
)


def build_supervisor_graph() -> StateGraph:
    """
    构建并编译 LangGraph 流水线。

    图结构（线性）:
        START
          → analyze_question      （提取格式要求）
          → decompose_question    （拆分子问题）
          → group_chat_execute    （GroupChat 多智能体协作）
          → synthesize            （综合生成答案）
          → format_answer         （格式化输出）
          → END
    """
    workflow = StateGraph(SupervisorState)

    # ---- 添加节点 ----
    workflow.add_node("analyze_question", analyze_question)
    workflow.add_node("decompose_question", decompose_question)
    workflow.add_node("group_chat_execute", group_chat_execute)
    workflow.add_node("synthesize", synthesize)
    workflow.add_node("format_answer", format_answer)

    # ---- 线性边 ----
    workflow.set_entry_point("analyze_question")
    workflow.add_edge("analyze_question", "decompose_question")
    workflow.add_edge("decompose_question", "group_chat_execute")
    workflow.add_edge("group_chat_execute", "synthesize")
    workflow.add_edge("synthesize", "format_answer")
    workflow.add_edge("format_answer", END)

    return workflow.compile()

# -*- coding: utf-8 -*-
"""
主图构建 — Send API 并行研究架构
流程：decompose_plan → [Send × N] research_branch → global_verify → global_summary → format_answer

路由逻辑：
- decompose_plan → route_to_research：
    - 有 pending 子问题 → Send("research_branch", ...) × N（并行执行）
    - 无 pending 子问题 → global_verify（直接验证已有证据）
- research_branch → global_verify（所有并行分支完成后聚合）
- global_verify → 条件路由：
    - 推理链充分 → global_summary
    - 超过 MAX_LOOPS → global_summary（强制）
    - 推理链不充分 → decompose_plan（奥卡姆剃刀：只为缺口生成新问题）
- global_summary → format_answer → END
"""
from langgraph.graph import END, StateGraph
from langgraph.types import Send

from config.settings import MAX_LOOPS
from graph.state import AgentState
from graph.nodes import (
    decompose_plan, research_branch,
    global_verify, global_summary, format_answer,
)


# ==================== 路由函数 ====================

def route_to_research(state: AgentState):
    """从 decompose_plan 路由到并行研究分支（Send API）"""
    pending = [sq for sq in state.get("sub_questions", []) if sq["status"] == "pending"]

    if not pending:
        # 无新子问题需要研究（可能所有都已完成），直接验证
        print(f"[Router] 无 pending 子问题，直接进入全局验证")
        return "global_verify"

    print(f"[Router] 分派 {len(pending)} 个并行研究分支")
    for sq in pending:
        print(f"  → Q{sq['id']} [{sq['priority']}] {sq['question']}")

    # 为每个 pending 子问题创建一个并行研究分支
    return [
        Send("research_branch", {
            "original_question": state["original_question"],
            "evidence_pool": state.get("evidence_pool", []),
            "current_branch_question": sq,
            "completed_question_ids": [],
        })
        for sq in pending
    ]


def route_after_verify(state: AgentState) -> str:
    """全局验证后路由 — 基于推理链充分性"""
    # 推理链充分 → 全局总结
    if state.get("is_sufficient", False):
        return "global_summary"

    # 超过最大循环 → 强制全局总结
    if state.get("loop_count", 0) >= MAX_LOOPS:
        return "global_summary"

    # 不充分 → 回到 decompose_plan（奥卡姆剃刀：只补缺口）
    return "decompose_plan"


# ==================== 构建主图 ====================

def build_graph() -> StateGraph:
    """构建 Send API 并行研究架构主图"""
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("decompose_plan", decompose_plan)
    workflow.add_node("research_branch", research_branch)
    workflow.add_node("global_verify", global_verify)
    workflow.add_node("global_summary", global_summary)
    workflow.add_node("format_answer", format_answer)

    # 入口 → 问题拆分规划
    workflow.set_entry_point("decompose_plan")

    # decompose_plan → 条件路由（Send 并行分支 或 直接验证）
    workflow.add_conditional_edges(
        "decompose_plan",
        route_to_research,
        {"global_verify": "global_verify"},
    )

    # research_branch → global_verify（所有并行分支完成后自动聚合）
    workflow.add_edge("research_branch", "global_verify")

    # global_verify → 条件路由
    workflow.add_conditional_edges(
        "global_verify",
        route_after_verify,
        {
            "global_summary": "global_summary",
            "decompose_plan": "decompose_plan",
        },
    )

    # global_summary → format_answer → END
    workflow.add_edge("global_summary", "format_answer")
    workflow.add_edge("format_answer", END)

    return workflow


def compile_graph():
    """编译并返回可执行的图"""
    graph = build_graph()
    return graph.compile()

# -*- coding: utf-8 -*-
"""
主图构建 — 流式证据 + 动态剪枝架构（Tree of Thought 剪枝范式）
流程：decompose_plan → parallel_research → global_verify → global_summary → format_answer

核心改进（相对于 Send API 版本）：
- 并行研究分支使用 ThreadPoolExecutor + as_completed 流式返回证据
- 每收到一条新证据立即执行快速充分性检查（Quick Check）
- 充分则立即终止剩余分支（动态剪枝 / 思维树剪枝）
- 高优先级子问题优先调度
- 消除 Send API 的"等待全部完成"瓶颈

路由逻辑：
- decompose_plan → parallel_research（线程池并行 + 流式证据 + 动态剪枝）
- parallel_research → global_verify
- global_verify → 条件路由：
    - 推理链充分 → global_summary
    - 超过 MAX_LOOPS → global_summary（强制）
    - 推理链不充分 → decompose_plan（奥卡姆剃刀：只为缺口生成新问题）
- global_summary → format_answer → END
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from langgraph.graph import END, StateGraph

from config.settings import MAX_LOOPS, MAX_PARALLEL_WORKERS, QUICK_CHECK_MIN_EVIDENCE
from graph.state import AgentState
from graph.research_subgraph import compile_research_subgraph
from graph.nodes import (
    decompose_plan,
    global_verify, global_summary, format_answer,
    quick_sufficiency_check,
)


_RESEARCH_SUBGRAPH = compile_research_subgraph()


def _run_single_branch(original_question, sq, evidence_snapshot, stop_event):
    """在线程中执行单个研究分支（子图包装器）。

    Args:
        original_question: 原始问题
        sq: 子问题字典
        evidence_snapshot: 证据池快照（只读，不会被其他线程修改）
        stop_event: 停止信号，set() 后跳过尚未开始的分支

    Returns:
        dict with 'evidence' and 'question_id', or None if skipped/failed
    """
    if stop_event.is_set():
        return None

    q_id = sq.get("id", "?")
    query = sq.get("question", "")
    print(f"\n[ResearchBranch] 处理 Q{q_id}: {query}")

    t0 = time.time()
    try:
        out = _RESEARCH_SUBGRAPH.invoke({
            "original_question": original_question,
            "evidence_pool": evidence_snapshot,
            "current_branch_question": sq,
        })
    except Exception as e:
        print(f"[ResearchBranch] Q{q_id} 异常: {e}")
        return None

    elapsed = time.time() - t0
    print(f"[ResearchBranch] Q{q_id} 子图完成，耗时: {elapsed:.1f}s")

    return {
        "evidence": out.get("evidence_pool", []),
        "question_id": q_id,
    }


# ==================== 核心节点：并行研究 + 流式证据 + 动态剪枝 ====================

def parallel_research(state: AgentState) -> dict:
    """并行研究节点 — 线程池 + 流式证据 + 动态剪枝。

    替代 Send API 的"等待全部完成"模式：
    - 所有子问题通过 ThreadPoolExecutor 并行执行
    - 每个子问题完成后立即流式返回证据到主线程
    - 触发快速充分性检查（QuickCheck），充分则剪枝剩余分支
    - 高优先级子问题优先调度
    """
    completed_set = set(state.get("completed_question_ids", []))
    all_sqs = list(state.get("sub_questions", []))
    pending = [
        sq for sq in all_sqs
        if sq["status"] == "pending" and sq["id"] not in completed_set
    ]

    if not pending:
        print(f"[ParallelResearch] 无 pending 子问题，直接通过")
        return {}

    # 按优先级排序：高 > 中 > 低（影响线程池调度顺序）
    priority_order = {"高": 0, "中": 1, "低": 2}
    pending.sort(key=lambda sq: priority_order.get(sq.get("priority", "中"), 1))

    print(f"\n[ParallelResearch] 启动 {len(pending)} 个并行研究分支（流式证据 + 动态剪枝）")
    for sq in pending:
        print(f"  → Q{sq['id']} [{sq['priority']}] {sq['question']}")

    original_question = state["original_question"]
    evidence_snapshot = list(state.get("evidence_pool", []))

    stop_event = threading.Event()
    new_evidence = []
    new_completed_ids = []

    workers = min(len(pending), MAX_PARALLEL_WORKERS)
    executor = ThreadPoolExecutor(max_workers=workers)

    futures = {}
    for sq in pending:
        fut = executor.submit(
            _run_single_branch, original_question, sq, evidence_snapshot, stop_event
        )
        futures[fut] = sq

    pruned_count = 0
    try:
        for fut in as_completed(futures):
            result = fut.result() if fut.done() else None
            if result is None:
                continue

            new_evidence.extend(result["evidence"])
            new_completed_ids.append(result["question_id"])

            # 如果已发出停止信号，收集已完成的结果但不再做检查
            if stop_event.is_set():
                continue

            # 快速充分性检查：证据数达到阈值且仍有未完成分支时触发
            total_evidence = evidence_snapshot + new_evidence
            remaining = len(pending) - len(new_completed_ids)

            if (len(total_evidence) >= QUICK_CHECK_MIN_EVIDENCE
                    and remaining > 0):
                print(f"\n[QuickCheck] 已完成 {len(new_completed_ids)}/{len(pending)} 分支，"
                      f"证据池: {len(total_evidence)} 条，剩余: {remaining}")

                is_sufficient, quick_answer = quick_sufficiency_check(
                    original_question, total_evidence
                )

                if is_sufficient:
                    print(f"[QuickCheck] ✂ 证据已充分！答案: {quick_answer}")
                    print(f"[QuickCheck] 剪枝 {remaining} 个剩余分支")
                    pruned_count = remaining
                    stop_event.set()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    # 更新子问题状态
    completed_id_set = set(new_completed_ids)
    for sq in all_sqs:
        if sq["id"] in completed_id_set and sq["status"] == "pending":
            sq["status"] = "done"

    # 标记被剪枝的子问题
    if pruned_count > 0:
        for sq in all_sqs:
            if sq["status"] == "pending" and sq["id"] not in completed_id_set:
                sq["status"] = "pruned"

    print(f"\n[ParallelResearch] 完成: {len(new_completed_ids)} 个分支，"
          f"新增证据: {len(new_evidence)} 条"
          + (f"，剪枝: {pruned_count} 个" if pruned_count else ""))

    return {
        "evidence_pool": new_evidence,
        "completed_question_ids": new_completed_ids,
        "sub_questions": all_sqs,
    }


# ==================== 路由函数 ====================

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
    """构建流式证据 + 动态剪枝架构主图"""
    workflow = StateGraph(AgentState)

    workflow.add_node("decompose_plan", decompose_plan)
    workflow.add_node("parallel_research", parallel_research)
    workflow.add_node("global_verify", global_verify)
    workflow.add_node("global_summary", global_summary)
    workflow.add_node("format_answer", format_answer)

    workflow.set_entry_point("decompose_plan")

    # decompose_plan → parallel_research（内部处理无 pending 情况）
    workflow.add_edge("decompose_plan", "parallel_research")

    # parallel_research → global_verify
    workflow.add_edge("parallel_research", "global_verify")

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

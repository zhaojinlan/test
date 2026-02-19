"""
LangGraph 状态定义
显式、可观测的状态设计，Supervisor 图的核心数据结构
"""

import operator
from typing import TypedDict, Annotated


class SupervisorState(TypedDict):
    """Supervisor 条件监督图的全局状态"""

    # ---- 输入（初始化后不变）----
    question: str                                   # 原始问题
    format_requirement: str                         # 从题目中提取的格式要求

    # ---- 问题拆分 ----
    sub_questions: list                             # [{id, content, resolved, result}]

    # ---- Supervisor 路由 ----
    next_action: str                                # RESEARCH / ANALYZE / VERIFY / SYNTHESIZE
    next_task: str                                  # 传给子代理的具体任务描述
    supervisor_reasoning: str                       # Supervisor 当前轮的推理过程

    # ---- 计数器 ----
    iteration_count: int                            # 当前迭代轮数
    max_iterations: int                             # 最大迭代轮数

    # ---- 累积证据（使用 add reducer）----
    evidence_pool: Annotated[list, operator.add]    # 所有子代理返回的证据

    # ---- 日志 ----
    reasoning_trace: Annotated[list, operator.add]  # 推理轨迹日志

    # ---- 输出 ----
    final_answer: str                               # 最终答案


def create_initial_state(question: str, max_iterations: int = 10) -> dict:
    """构造初始状态字典"""
    return {
        "question": question,
        "format_requirement": "",
        "sub_questions": [],
        "next_action": "",
        "next_task": "",
        "supervisor_reasoning": "",
        "iteration_count": 0,
        "max_iterations": max_iterations,
        "evidence_pool": [],
        "reasoning_trace": [],
        "final_answer": "",
    }

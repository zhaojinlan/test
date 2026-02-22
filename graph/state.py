# -*- coding: utf-8 -*-
"""
LangGraph 状态定义 — Send API 并行研究架构
核心设计：
- 使用 LangGraph Send API 实现子问题的并行研究
- Evidence：证据池（累积式 session memory）
- SubQuestion：带优先级子问题
- AgentState：主图状态，支持并行分支 + 推理链评估
"""
import operator
from typing import Annotated, List, TypedDict


# ==================== 证据 ====================

class Evidence(TypedDict):
    """证据池中的单条证据"""
    id: int
    source_question_id: int          # 产生该证据的子问题 ID
    statement: str                   # 陈述性语句（一句话总结）
    source_urls: List[str]
    reliability: str                 # high / medium / low


# ==================== 子问题 ====================

class SubQuestion(TypedDict):
    """带优先级的子问题"""
    id: int
    question: str                    # 搜索查询（bocha用自然语言句子，serper用关键词）
    purpose: str                     # 搜索目的
    priority: str                    # 高 / 中 / 低
    status: str                      # pending / done / pruned
    search_engine: str               # bocha / serper / baike
    raw_results: str                 # 原始搜索结果文本
    reflection: str                  # 反思后的有用信息


# ==================== 主图状态 ====================

class AgentState(TypedDict):
    """主图状态 — 支持 Send API 并行分支"""
    # 输入
    original_question: str

    # 拆分规划
    sub_questions: List[SubQuestion]
    anchor_analysis: str             # 锚点分析结果

    # 证据池（session memory，累积式）
    evidence_pool: Annotated[list, operator.add]

    # 并行分支控制（Send API）
    current_branch_question: dict    # 由 Send 设置，指定当前分支处理的子问题
    completed_question_ids: Annotated[list, operator.add]  # 已完成的子问题 ID（累积）

    # 全局验证（推理链评估，取代刚性覆盖率）
    reasoning_chain: str             # 构建的推理链
    is_sufficient: bool              # 推理链是否充分覆盖问题

    # 循环控制
    loop_count: int
    force_passed: bool               # 是否因达到 MAX_LOOPS 而强制通过

    # 输出
    final_answer: str
    formatted_answer: str

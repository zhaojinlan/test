"""
LangGraph 节点函数
每个函数接收 SupervisorState，返回状态更新 dict
"""

import re
import logging
from graph.state import SupervisorState
from utils.llm_client import call_llm
from agents.react_wrapper import GroupChatOrchestrator
from utils.post_process import post_process_answer

logger = logging.getLogger(__name__)


# ======================================================================
# 1. 问题分析节点 —— 提取格式要求
# ======================================================================
def analyze_question(state: SupervisorState) -> dict:
    question = state["question"]

    print("\n" + "=" * 70)
    print("【节点】问题分析 —— 提取格式要求")
    print("=" * 70)

    prompt = f"""\
请仔细阅读以下问题，提取其中对答案格式的明确要求。

问题：
{question}

如果题目中声明了回答格式（如"格式形如：XXX"），请原样输出该格式要求。
如果没有明确格式要求，请输出"无特殊格式要求"。
只输出格式要求本身，不要添加任何解释。"""

    fmt = call_llm(prompt)
    print(f"  格式要求: {fmt}")

    return {
        "format_requirement": fmt.strip(),
        "reasoning_trace": [f"[分析] 格式要求: {fmt.strip()}"],
    }


# ======================================================================
# 2. 问题拆分节点
# ======================================================================
def decompose_question(state: SupervisorState) -> dict:
    question = state["question"]

    print("\n" + "=" * 70)
    print("【节点】问题拆分 —— 将复杂问题分解为子问题")
    print("=" * 70)

    prompt = f"""\
你是一位问题拆解专家。请将以下复杂问题拆分为 2-5 个可独立搜索的子问题。

原始问题：
{question}

拆分原则：
1. 每个子问题应聚焦于一个具体的实体、关系或事实。
2. 子问题之间形成推理链，前面的子问题为后面的提供线索。
3. 子问题应该是具体的、可搜索的。

请按以下格式输出：
子问题1: <描述>
子问题2: <描述>
...

只输出子问题列表。"""

    response = call_llm(prompt)

    # 解析子问题
    sub_questions = []
    pattern = r"子问题\s*(\d+)\s*[:：]\s*(.+?)(?=子问题\s*\d+|$)"
    matches = re.findall(pattern, response, re.DOTALL)

    for idx, (num, desc) in enumerate(matches):
        sq = {
            "id": f"sq_{idx + 1}",
            "content": desc.strip(),
            "resolved": False,
            "result": "",
        }
        sub_questions.append(sq)
        print(f"  子问题 {idx + 1}: {desc.strip()[:80]}")

    # 兜底：如果解析失败，整个问题作为一个子问题
    if not sub_questions:
        sub_questions = [{
            "id": "sq_1",
            "content": question,
            "resolved": False,
            "result": "",
        }]
        print(f"  （未成功拆分，使用原始问题）")

    print(f"\n  共拆分为 {len(sub_questions)} 个子问题")

    return {
        "sub_questions": sub_questions,
        "reasoning_trace": [f"[拆分] 生成 {len(sub_questions)} 个子问题"],
    }


# ======================================================================
# 3. GroupChat 多智能体协作节点
# ======================================================================
def group_chat_execute(state: SupervisorState) -> dict:
    """
    核心执行节点：启动 GroupChat，让 researcher、analyst、verifier
    在同一对话中协作，实时交叉验证，直到达成共识。
    """
    question = state["question"]
    sub_questions = state["sub_questions"]

    print("\n" + "=" * 70)
    print("【节点】GroupChat 多智能体协作")
    print("=" * 70)

    # 构建已有上下文
    context = ""
    if state.get("evidence_pool"):
        context_parts = ["已有信息："]
        for ev in state["evidence_pool"]:
            context_parts.append(
                f"- [{ev.get('source', '')}] {ev.get('content', '')[:300]}"
            )
        context = "\n".join(context_parts)

    # 创建并运行 GroupChat
    orchestrator = GroupChatOrchestrator()
    result = orchestrator.run(
        question=question,
        sub_questions=sub_questions,
        context=context,
    )

    # 从 GroupChat 历史中提取证据
    evidence_list = orchestrator.extract_evidence_from_history()

    return {
        "evidence_pool": evidence_list if evidence_list else [
            {"source": "group_chat", "content": result}
        ],
        "final_answer": result,
        "reasoning_trace": [f"[GroupChat] 协作完成，结论: {result[:100]}"],
    }


# ======================================================================
# 4. 综合节点 —— 汇总所有证据，生成最终答案
# ======================================================================
def synthesize(state: SupervisorState) -> dict:
    question = state["question"]
    fmt = state["format_requirement"]
    evidence = state["evidence_pool"]

    print("\n" + "=" * 70)
    print("【节点】综合汇总 —— 生成最终答案")
    print("=" * 70)

    evidence_text = ""
    for i, ev in enumerate(evidence, 1):
        evidence_text += f"\n证据{i} [{ev.get('source','')}]:\n{ev.get('content','')}\n"

    prompt = f"""\
请根据以下所有证据，回答原始问题。

原始问题：{question}

格式要求：{fmt}

收集到的所有证据：
{evidence_text}

【输出规则——极其重要，必须严格遵守】
1. 只输出答案本身（名词、数字或短语），绝对不要输出任何解释、推理过程、前缀（如"答案是"）。
2. 如果题目声明了回答格式，严格遵循该格式。
3. 如果题目没有特殊格式声明，答案语言与问题语言保持一致（中文问题→中文答案，英文问题→英文答案）。
4. 如果答案是数字，输出整数形式。
5. 如果答案包含多个实体，用逗号加空格分隔（如: entity1, entity2）。
6. 不要输出"根据……"、"答案是……"、"无法确定"等任何非答案内容。如果确实无法确定，输出你认为最可能的答案。"""

    answer = call_llm(prompt)
    answer = answer.strip()

    print(f"  综合答案: {answer}")

    return {
        "final_answer": answer,
        "reasoning_trace": [f"[综合] 最终答案: {answer}"],
    }


# ======================================================================
# 8. 格式化输出节点
# ======================================================================
def format_answer(state: SupervisorState) -> dict:
    raw = state["final_answer"]
    question = state["question"]
    fmt_req = state.get("format_requirement", "")

    print("\n" + "=" * 70)
    print("【节点】答案格式化")
    print("=" * 70)

    # ---- 第一步：LLM 提取纯净答案 ----
    extract_prompt = f"""\
你是一个答案格式提取器。你的任务是从下面的原始回答中提取出纯净的最终答案。

原始问题：{question}
格式要求：{fmt_req if fmt_req else "无特殊格式要求"}
原始回答：{raw}

【提取规则】
1. 只输出答案本身（名词、数字或短语），去掉所有解释性文字。
2. 如果原始回答中包含"答案是XX"、"因此XX"等句式，只提取 XX 部分。
3. 如果题目声明了格式要求（如"格式形如：Alibaba Group Limited"），严格按该格式输出。
4. 如果题目没有特殊格式声明，答案语言与问题语言一致（中文问题→中文答案，英文问题→英文答案）。
5. 数值答案输出整数形式（如 42，不要 42.0）。
6. 多实体答案用逗号加空格分隔。
7. 绝对不要输出任何解释，只输出最终答案。"""

    try:
        extracted = call_llm(extract_prompt).strip()
    except Exception as e:
        logger.error(f"[format_answer] LLM 提取失败: {e}")
        extracted = raw.strip()

    # ---- 第二步：后处理（纯规则层）----
    processed = post_process_answer(extracted)

    # 如果格式要求含大写示例，保留 LLM 提取的原始大小写
    if fmt_req and any(c.isupper() for c in fmt_req):
        processed = extracted.strip()
        processed = re.sub(r",\s*", ", ", processed)
        processed = re.sub(r";\s*", "; ", processed)

    print(f"  原始答案  : {raw}")
    print(f"  LLM提取   : {extracted}")
    print(f"  处理后答案: {processed}")

    return {
        "final_answer": processed,
        "reasoning_trace": [f"[格式化] {raw} -> {extracted} -> {processed}"],
    }

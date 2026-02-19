"""
LangGraph 节点函数
每个函数接收 SupervisorState，返回状态更新 dict
"""

import re
import logging
from graph.state import SupervisorState
from utils.llm_client import call_llm
from agents.react_wrapper import ReactSubAgent
from agents.prompts import RESEARCH_SYSTEM_PROMPT, ANALYSIS_SYSTEM_PROMPT, VERIFICATION_SYSTEM_PROMPT
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
# 3. Supervisor 决策节点（外层 ReAct 的 Thought）
# ======================================================================
def supervisor_decide(state: SupervisorState) -> dict:
    question = state["question"]
    sub_questions = state["sub_questions"]
    evidence = state["evidence_pool"]
    iteration = state["iteration_count"]
    max_iter = state["max_iterations"]

    print("\n" + "=" * 70)
    print(f"【Supervisor 决策】第 {iteration + 1}/{max_iter} 轮")
    print("=" * 70)

    # 构建证据摘要
    evidence_summary = ""
    if evidence:
        for i, ev in enumerate(evidence, 1):
            src = ev.get("source", "unknown")
            content = ev.get("content", "")[:300]
            evidence_summary += f"\n  证据{i} [{src}]: {content}"
    else:
        evidence_summary = "\n  （暂无证据）"

    # 构建子问题状态
    sq_status = ""
    for sq in sub_questions:
        status = "✓已解决" if sq.get("resolved") else "○待解决"
        sq_status += f"\n  [{status}] {sq['content'][:60]}"

    prompt = f"""\
你是多智能体系统的监督者（Supervisor）。请根据当前系统状态做出路由决策。

原始问题：{question}

子问题列表：{sq_status}

已收集证据：{evidence_summary}

当前轮次：{iteration + 1}/{max_iter}

请分析当前状态，决定下一步操作。你的选择：
- RESEARCH : 需要更多广度搜索，收集新线索
- ANALYZE  : 已有初步线索，需要对某方面深入分析
- VERIFY   : 已有候选答案，需要验证准确性
- SYNTHESIZE : 信息已充分（或已到最后轮次），综合得出最终答案

请按以下格式回答：
Thought: <你对当前状态的分析>
Decision: <RESEARCH 或 ANALYZE 或 VERIFY 或 SYNTHESIZE>
Task: <给子代理的具体任务描述（如果选择 SYNTHESIZE 可留空）>"""

    response = call_llm(prompt)

    # 解析决策
    decision_match = re.search(r"Decision:\s*(RESEARCH|ANALYZE|VERIFY|SYNTHESIZE)", response, re.IGNORECASE)
    decision = decision_match.group(1).upper() if decision_match else "RESEARCH"

    task_match = re.search(r"Task:\s*(.+?)$", response, re.DOTALL)
    task_desc = task_match.group(1).strip() if task_match else question

    thought_match = re.search(r"Thought:\s*(.+?)(?=Decision:|$)", response, re.DOTALL)
    reasoning = thought_match.group(1).strip() if thought_match else response[:200]

    # 最后一轮强制 SYNTHESIZE
    if iteration + 1 >= max_iter and decision != "SYNTHESIZE":
        decision = "SYNTHESIZE"
        print(f"  ⚠ 已到最大轮次，强制 SYNTHESIZE")

    print(f"  Thought  : {reasoning[:120]}")
    print(f"  Decision : {decision}")
    print(f"  Task     : {task_desc[:100]}")

    return {
        "next_action": decision,
        "next_task": task_desc,
        "supervisor_reasoning": reasoning,
        "iteration_count": iteration + 1,
        "reasoning_trace": [f"[Supervisor 轮{iteration+1}] Decision={decision}: {reasoning[:80]}"],
    }


# ======================================================================
# 4. 研究执行节点（外层 ReAct 的 Action —— 调用研究子代理）
# ======================================================================
def research_execute(state: SupervisorState) -> dict:
    task = state["next_task"]
    question = state["question"]

    print("\n" + "=" * 70)
    print("【执行】研究代理（广度搜索 · CoT）")
    print("=" * 70)

    # 构建上下文
    context_parts = [f"原始问题：{question}"]
    if state["evidence_pool"]:
        context_parts.append("已知信息：")
        for ev in state["evidence_pool"][-3:]:  # 最近3条证据
            context_parts.append(f"- {ev.get('content', '')[:200]}")
    context = "\n".join(context_parts)

    agent = ReactSubAgent(name="research_agent", system_prompt=RESEARCH_SYSTEM_PROMPT)
    result = agent.run(task=task, context=context)

    return {
        "evidence_pool": [{"source": "research", "content": result}],
        "reasoning_trace": [f"[Research] {result[:100]}"],
    }


# ======================================================================
# 5. 分析执行节点
# ======================================================================
def analysis_execute(state: SupervisorState) -> dict:
    task = state["next_task"]
    question = state["question"]

    print("\n" + "=" * 70)
    print("【执行】分析代理（深度分析 · ToT）")
    print("=" * 70)

    context_parts = [f"原始问题：{question}"]
    if state["evidence_pool"]:
        context_parts.append("已收集的线索：")
        for ev in state["evidence_pool"]:
            context_parts.append(f"- [{ev.get('source','')}] {ev.get('content','')[:300]}")
    context = "\n".join(context_parts)

    agent = ReactSubAgent(name="analysis_agent", system_prompt=ANALYSIS_SYSTEM_PROMPT)
    result = agent.run(task=task, context=context)

    return {
        "evidence_pool": [{"source": "analysis", "content": result}],
        "reasoning_trace": [f"[Analysis] {result[:100]}"],
    }


# ======================================================================
# 6. 验证执行节点
# ======================================================================
def verify_execute(state: SupervisorState) -> dict:
    task = state["next_task"]
    question = state["question"]

    print("\n" + "=" * 70)
    print("【执行】验证代理（事实核查 · CoT）")
    print("=" * 70)

    context_parts = [f"原始问题：{question}"]
    if state["evidence_pool"]:
        context_parts.append("待验证的信息：")
        for ev in state["evidence_pool"]:
            context_parts.append(f"- [{ev.get('source','')}] {ev.get('content','')[:300]}")
    context = "\n".join(context_parts)

    agent = ReactSubAgent(name="verify_agent", system_prompt=VERIFICATION_SYSTEM_PROMPT)
    result = agent.run(task=task, context=context)

    return {
        "evidence_pool": [{"source": "verification", "content": result}],
        "reasoning_trace": [f"[Verify] {result[:100]}"],
    }


# ======================================================================
# 7. 综合节点 —— 汇总所有证据，生成最终答案
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

请综合以上信息，给出准确的最终答案。
注意：
1. 答案必须直接回应问题。
2. 如果问题要求特定格式，严格遵守。
3. 只输出答案本身，不要添加解释或前缀。
4. 答案一般是名词或数字，保证不含无关信息。"""

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

    print("\n" + "=" * 70)
    print("【节点】答案格式化")
    print("=" * 70)

    fmt_req = state.get("format_requirement", "")

    # 如果格式要求包含大写字母示例（如 "Alibaba Group Limited"），不做小写转换
    if fmt_req and any(c.isupper() for c in fmt_req) and "形如" in fmt_req:
        processed = raw.strip()
        # 只做基本清理
        processed = re.sub(r",\s*", ", ", processed)
        processed = re.sub(r";\s*", "; ", processed)
    else:
        processed = post_process_answer(raw)

    print(f"  原始答案  : {raw}")
    print(f"  处理后答案: {processed}")

    return {
        "final_answer": processed,
        "reasoning_trace": [f"[格式化] {raw} -> {processed}"],
    }

# -*- coding: utf-8 -*-
"""
所有图节点函数 — 流式证据 + 动态剪枝架构
节点：decompose_plan / global_verify / global_summary / format_answer
辅助：quick_sufficiency_check（供 parallel_research 节点调用）
"""
import re
from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from config.settings import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME,
    MAX_SEARCH_RETRIES, MAX_LOOPS, MAX_BAIKE_VERIFY,
)
from graph.state import AgentState, SubQuestion, Evidence
from tools.search import bocha_search, serper_search, auto_search, fetch_url_content, baike_search
from agents.prompts import (
    DECOMPOSE_PLAN_PROMPT, RESEARCH_SEARCH_PROMPT, RESEARCH_REFLECT_PROMPT,
    RESEARCH_EVIDENCE_PROMPT, GLOBAL_VERIFY_PROMPT,
    GLOBAL_SUMMARY_PROMPT, FORMAT_ANSWER_PROMPT,
    QUICK_CHECK_PROMPT,
)


def _get_llm(temperature: float = 0.2) -> ChatOpenAI:
    return ChatOpenAI(
        model=LLM_MODEL_NAME,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        temperature=temperature,
    )


def _evidence_summary(evidence_pool: list) -> str:
    """格式化证据池为可读文本"""
    if not evidence_pool:
        return "（暂无证据）"
    lines = []
    for e in evidence_pool:
        lines.append(f"  [E{e['id']}] (可靠性:{e['reliability']}) {e['statement']}")
    return "\n".join(lines)


def _sub_questions_summary(sub_questions: List[SubQuestion]) -> str:
    """格式化子问题列表为可读文本"""
    if not sub_questions:
        return "（暂无子问题）"
    lines = []
    for sq in sub_questions:
        status_icon = {"done": "✓", "pending": "○", "pruned": "✗"}.get(sq["status"], "?")
        lines.append(f"  [{status_icon}] Q{sq['id']} [{sq['priority']}] {sq['question']}")
    return "\n".join(lines)


def _completed_questions_summary(sub_questions: List[SubQuestion], completed_ids: list) -> str:
    """格式化已完成的子问题列表"""
    completed_set = set(completed_ids or [])
    done = [sq for sq in sub_questions if sq["id"] in completed_set or sq["status"] == "done"]
    if not done:
        return "（暂无已完成的子问题）"
    lines = []
    for sq in done:
        lines.append(f"  [✓] Q{sq['id']}: {sq['question']}")
    return "\n".join(lines)


def _failed_queries_summary(sub_questions: List[SubQuestion], evidence_pool: list, completed_ids: list) -> str:
    """构建已尝试搜索方向及其结果的摘要，帮助 DecomposePlan 避免重复"""
    completed_set = set(completed_ids or [])
    lines = []
    for sq in sub_questions:
        if sq["id"] in completed_set or sq["status"] == "done":
            # 查找该子问题对应的证据
            matching = [e for e in evidence_pool if e.get("source_question_id") == sq["id"]]
            if matching:
                e = matching[0]
                result_brief = e["statement"][:150]
                lines.append(f"  Q{sq['id']}: {sq['question']}")
                lines.append(f"    → 结果({e['reliability']}): {result_brief}")
            else:
                lines.append(f"  Q{sq['id']}: {sq['question']} → 无结果")
    return "\n".join(lines) if lines else "（暂无）"


# 高价值页面 URL 模式（百科、维基等信息密集型页面）
_HIGH_VALUE_URL_PATTERNS = [
    "baike.baidu.com",
    "baike.sogou.com",
]


def _extract_urls_from_results(raw_results: str) -> list:
    """从搜索结果文本中提取所有 URL"""
    urls = re.findall(r'https?://[^\s\)）\]]+', raw_results)
    return urls


def _deep_read_promising_urls(raw_results: str, max_reads: int = 2) -> str:
    """从搜索结果中识别高价值 URL（百科/wiki 类），读取完整页面内容。"""
    urls = _extract_urls_from_results(raw_results)
    read_contents = []

    for url in urls:
        if len(read_contents) >= max_reads:
            break
        if any(pattern in url for pattern in _HIGH_VALUE_URL_PATTERNS):
            print(f"  [DeepRead] 读取高价值页面: {url}")
            content = fetch_url_content(url, max_chars=15000)
            if "[URL读取失败]" not in content and "[URL内容]" in content and len(content) > 100:
                read_contents.append(content)

    return "\n\n".join(read_contents) if read_contents else ""




# ==================== 节点 1：问题拆分和规划（ToT + 奥卡姆剃刀） ====================

def decompose_plan(state: AgentState) -> dict:
    """问题拆分和规划节点 — 奥卡姆剃刀原则，只为缺口生成子问题"""
    print(f"\n{'='*60}")
    print(f"[DecomposePlan] 分析问题并规划搜索策略（奥卡姆剃刀）...")
    print(f"{'='*60}")

    llm = _get_llm()

    existing_evidence = _evidence_summary(state.get("evidence_pool", []))
    completed_questions = _completed_questions_summary(
        state.get("sub_questions", []),
        state.get("completed_question_ids", []),
    )

    # 先更新已有子问题状态（标记已完成的）
    completed_set = set(state.get("completed_question_ids", []))
    all_questions = list(state.get("sub_questions", []))
    for sq in all_questions:
        if sq["id"] in completed_set and sq["status"] == "pending":
            sq["status"] = "done"

    failed_queries = _failed_queries_summary(
        state.get("sub_questions", []),
        state.get("evidence_pool", []),
        state.get("completed_question_ids", []),
    )

    prompt = DECOMPOSE_PLAN_PROMPT.format(
        question=state["original_question"],
        existing_evidence=existing_evidence,
        completed_questions=completed_questions,
        failed_queries=failed_queries,
    )

    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()

    # 解析知识推理（兼容旧版"锚点分析"）
    anchor_analysis = ""
    for section_header in ["## 知识推理", "## 锚点分析"]:
        if section_header in content:
            anchor_section = content.split(section_header)[1]
            anchor_analysis = anchor_section.split("## 子问题列表")[0].strip() if "## 子问题列表" in anchor_section else anchor_section.strip()
            break

    # 解析子问题列表
    existing_ids = {sq["id"] for sq in all_questions}
    next_id = max(existing_ids) + 1 if existing_ids else 1

    new_questions: List[SubQuestion] = []
    current_q = {"question": "", "engine": "both", "priority": "中", "purpose": ""}

    sq_section = ""
    if "## 子问题列表" in content:
        sq_section = content.split("## 子问题列表")[1].strip()

    for line in sq_section.split("\n"):
        line = line.strip()
        if not line:
            continue

        if re.match(r'^\d+[\.\)）、]', line):
            if current_q["question"]:
                new_questions.append(SubQuestion(
                    id=next_id,
                    question=current_q["question"],
                    purpose=current_q["purpose"],
                    priority=current_q["priority"],
                    status="pending",
                    search_engine=current_q["engine"],
                    raw_results="",
                    reflection="",
                ))
                next_id += 1

            stripped = re.sub(r'^\d+[\.\)）、]\s*', '', line).strip()
            if "搜索查询：" in stripped or "搜索查询:" in stripped:
                current_q["question"] = stripped.split("搜索查询：")[-1].split("搜索查询:")[-1].strip()
            elif "子问题：" in stripped or "子问题:" in stripped:
                current_q["question"] = stripped.split("子问题：")[-1].split("子问题:")[-1].strip()
            elif "问题：" in stripped or "问题:" in stripped:
                current_q["question"] = stripped.split("问题：")[-1].split("问题:")[-1].strip()
            else:
                current_q["question"] = stripped
            # 清除 markdown 格式泄漏（LLM 常输出 **问题** 或 `查询`）
            current_q["question"] = re.sub(r'^[\*\#\`\s]+', '', current_q["question"])
            current_q["question"] = re.sub(r'[\*\#\`]+$', '', current_q["question"]).strip()
            # 去除引号包裹（LLM 有时用引号包裹查询）
            if current_q["question"].startswith('"') and current_q["question"].endswith('"'):
                current_q["question"] = current_q["question"][1:-1].strip()
            if current_q["question"].startswith('`') and current_q["question"].endswith('`'):
                current_q["question"] = current_q["question"][1:-1].strip()
            current_q["engine"] = "both"
            current_q["priority"] = "中"
            current_q["purpose"] = ""

        elif "引擎：" in line or "引擎:" in line:
            eng = line.split("引擎：")[-1].split("引擎:")[-1].strip().lower()
            if "baike" in eng:
                current_q["engine"] = "baike"
            elif "bocha" in eng:
                current_q["engine"] = "bocha"
            elif "serper" in eng:
                current_q["engine"] = "serper"
            else:
                current_q["engine"] = "both"

        elif "重要性：" in line or "重要性:" in line:
            pri = line.split("重要性：")[-1].split("重要性:")[-1].strip()
            if "高" in pri:
                current_q["priority"] = "高"
            elif "低" in pri:
                current_q["priority"] = "低"
            else:
                current_q["priority"] = "中"

        elif "目的：" in line or "目的:" in line:
            current_q["purpose"] = line.split("目的：")[-1].split("目的:")[-1].strip()
        elif "期望发现：" in line or "期望发现:" in line:
            current_q["purpose"] = line.split("期望发现：")[-1].split("期望发现:")[-1].strip()
        elif "验证目标：" in line or "验证目标:" in line:
            current_q["purpose"] = line.split("验证目标：")[-1].split("验证目标:")[-1].strip()

    if current_q["question"]:
        new_questions.append(SubQuestion(
            id=next_id,
            question=current_q["question"],
            purpose=current_q["purpose"] or "获取相关信息",
            priority=current_q["priority"],
            status="pending",
            search_engine=current_q["engine"],
            raw_results="",
            reflection="",
        ))

    # Fallback
    if not new_questions:
        new_questions.append(SubQuestion(
            id=next_id,
            question=state["original_question"],
            purpose="直接搜索原始问题",
            priority="高",
            status="pending",
            search_engine="both",
            raw_results="",
            reflection="",
        ))

    # 过滤占位符，限制数量（奥卡姆剃刀：最多4个）
    placeholder_pat = re.compile(r'\[.+?\]')
    filtered = [nq for nq in new_questions if not placeholder_pat.search(nq["question"])]
    if not filtered:
        filtered = new_questions[:1]
    filtered = filtered[:4]

    # 合并到已有子问题（去重）
    existing_texts = {sq["question"] for sq in all_questions}
    for nq in filtered:
        if nq["question"] not in existing_texts:
            all_questions.append(nq)

    print(f"[DecomposePlan] 知识推理:\n{anchor_analysis}")

    done_qs = [sq for sq in all_questions if sq["status"] == "done"]
    pending_qs = [sq for sq in all_questions if sq["status"] == "pending"]
    pruned_qs = [sq for sq in all_questions if sq["status"] == "pruned"]
    print(f"[DecomposePlan] 新增 {len(filtered)} 个子问题，"
          f"总计 {len(all_questions)} (待处理: {len(pending_qs)}, 已完成: {len(done_qs)}, 已剪枝: {len(pruned_qs)})")
    if done_qs:
        for sq in done_qs:
            print(f"  [✓] Q{sq['id']}: {sq['question'][:60]}")
    for sq in pending_qs:
        print(f"  [pending][{sq['priority']}] Q{sq['id']}: {sq['question']}")
    if pruned_qs:
        for sq in pruned_qs:
            print(f"  [✗] Q{sq['id']}: {sq['question'][:60]}")

    return {
        "sub_questions": all_questions,
        "anchor_analysis": anchor_analysis,
    }


# ==================== 快速充分性检查（供 parallel_research 动态剪枝调用） ====================

def quick_sufficiency_check(question: str, evidence_pool: list) -> tuple:
    """快速充分性检查 — 轻量级 LLM 调用，判断当前证据是否足以回答问题。

    Returns:
        (is_sufficient: bool, quick_answer: str)
    """
    llm = _get_llm(temperature=0.0)
    evidence_text = _evidence_summary(evidence_pool)

    prompt = QUICK_CHECK_PROMPT.format(
        question=question,
        evidence_count=len(evidence_pool),
        evidence=evidence_text,
    )

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content.strip()

        is_sufficient = "充分" in content and "不充分" not in content
        answer = ""
        if "答案：" in content or "答案:" in content:
            answer = content.split("答案：")[-1].split("答案:")[-1].split("\n")[0].strip()

        print(f"[QuickCheck] 判断: {'充分' if is_sufficient else '不充分'}"
              + (f"，答案: {answer}" if answer else ""))

        return is_sufficient, answer
    except Exception as e:
        print(f"[QuickCheck] 异常: {e}")
        return False, ""


# ==================== 节点 3：全局验证（GoT — 推理链评估） ====================

def global_verify(state: AgentState) -> dict:
    """全局验证节点 — 评估推理链完整性（取代刚性覆盖率百分比）"""
    loop = state.get("loop_count", 0) + 1
    evidence_pool = state.get("evidence_pool", [])
    print(f"\n{'='*60}")
    print(f"[GlobalVerify] 推理链评估（第 {loop} 轮）")
    print(f"{'='*60}")

    # 先更新子问题状态
    completed_set = set(state.get("completed_question_ids", []))
    sub_questions = list(state.get("sub_questions", []))
    for sq in sub_questions:
        if sq["id"] in completed_set and sq["status"] == "pending":
            sq["status"] = "done"

    done_count = sum(1 for sq in sub_questions if sq["status"] == "done")
    print(f"[GlobalVerify] 子问题: {done_count}/{len(sub_questions)} 已完成 | 证据池: {len(evidence_pool)} 条")

    llm = _get_llm(temperature=0.1)

    sq_summary = _sub_questions_summary(sub_questions)
    all_evidence = _evidence_summary(state.get("evidence_pool", []))

    prompt = GLOBAL_VERIFY_PROMPT.format(
        question=state["original_question"],
        sub_questions_summary=sq_summary,
        all_evidence=all_evidence,
    )

    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()

    # 剥离 markdown 格式符号后解析
    content_clean = content.replace("**", "").replace("*", "")
    content_clean = re.sub(r'^[\s\-]+', '', content_clean, flags=re.MULTILINE)

    is_sufficient = False
    best_answer = ""
    reasoning_chain = ""

    # 提取推理链
    if "## 推理链" in content_clean:
        rc_section = content_clean.split("## 推理链")[1]
        reasoning_chain = rc_section.split("## 判断")[0].strip() if "## 判断" in rc_section else rc_section.strip()

    # 提取判断
    if "## 判断" in content_clean:
        judgment = content_clean.split("## 判断")[1].strip()
        if "充分性：充分" in judgment or "充分性:充分" in judgment or "充分性： 充分" in judgment:
            is_sufficient = True
        if "当前最佳答案：" in judgment or "当前最佳答案:" in judgment:
            best_answer = judgment.split("当前最佳答案：")[-1].split("当前最佳答案:")[-1].split("\n")[0].strip()

    # 循环次数达到上限，强制通过
    force_passed = False
    if loop >= MAX_LOOPS:
        force_passed = True
        is_sufficient = True
        print(f"[GlobalVerify] 达到最大循环次数 {MAX_LOOPS}，强制通过")

    print(f"[GlobalVerify] 充分性: {'充分' if is_sufficient else '不充分'}")
    if best_answer:
        print(f"[GlobalVerify] 当前最佳答案: {best_answer}")
    print(f"[GlobalVerify] 完整验证输出:\n{content}")

    result = {
        "sub_questions": sub_questions,
        "reasoning_chain": reasoning_chain,
        "is_sufficient": is_sufficient,
        "loop_count": loop,
        "force_passed": force_passed,
    }

    if best_answer:
        result["final_answer"] = best_answer

    return result


# ==================== 节点 4：全局总结（CoT） ====================

def global_summary(state: AgentState) -> dict:
    """全局总结节点 — 使用推理链推导最终答案"""
    print(f"\n{'='*60}")
    print(f"[GlobalSummary] 生成最终答案...")
    print(f"{'='*60}")

    llm = _get_llm(temperature=0.1)

    all_evidence = _evidence_summary(state.get("evidence_pool", []))
    reasoning_chain = state.get("reasoning_chain", "（无推理链）")

    prompt = GLOBAL_SUMMARY_PROMPT.format(
        question=state["original_question"],
        all_evidence=all_evidence,
        reasoning_chain=reasoning_chain[:6000],
    )

    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()

    # 剥离 markdown 格式后提取答案
    content_clean = content.replace("**", "").replace("*", "").replace("`", "")

    answer = ""
    if "## 最终答案" in content_clean:
        answer = content_clean.split("## 最终答案")[1].strip().split("\n")[0].strip()
    elif "最终答案" in content_clean:
        answer = content_clean.split("最终答案")[-1].strip().split("\n")[0].strip().lstrip("：:").strip()

    # 清理残余格式符号，检查是否有实质内容
    answer = re.sub(r'^[\s\*\#\`：:]+', '', answer).strip()
    answer = re.sub(r'[\s\*\#\`]+$', '', answer).strip()

    if not answer:
        # fallback: 使用验证阶段的最佳答案
        answer = state.get("final_answer", "")

    if not answer:
        for line in reversed(content_clean.split("\n")):
            line = line.strip()
            if line and len(line) > 3:
                answer = line
                break

    print(f"[GlobalSummary] 最终答案: {answer}")

    return {"final_answer": answer}


# ==================== 节点 5：答案格式化 ====================

def _extract_final_answer(text: str) -> str:
    """从 LLM 格式化输出中提取最终答案。
    CoT prompt 可能导致 LLM 输出推理过程，此函数提取最后的实质答案行。"""
    text = text.strip()
    # 单行输出 → 直接返回
    if "\n" not in text:
        return text
    # 多行输出 → LLM 可能泄漏了推理过程，取最后一个非空实质行
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return text
    # 从后往前找第一行不像推理过程的内容（不以步骤/分析/标记开头）
    reasoning_prefixes = ("步骤", "###", "##", "#", "分析", "- ", "* ", "**")
    for line in reversed(lines):
        if not line.startswith(reasoning_prefixes):
            return line
    return lines[-1]


def format_answer(state: AgentState) -> dict:
    """格式化最终答案"""
    print(f"\n[FormatAnswer] 格式化...")

    raw = state.get("final_answer", "")
    if not raw:
        print(f"[FormatAnswer] 无答案可格式化")
        return {"formatted_answer": ""}

    llm = _get_llm(temperature=0.0)
    prompt = FORMAT_ANSWER_PROMPT.format(
        question=state["original_question"],
        raw_answer=raw,
    )

    response = llm.invoke([HumanMessage(content=prompt)])
    formatted = _extract_final_answer(response.content)

    print(f"[FormatAnswer] 最终输出: {formatted}")

    return {"formatted_answer": formatted}

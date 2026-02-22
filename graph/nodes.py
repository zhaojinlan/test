# -*- coding: utf-8 -*-
"""
所有图节点函数 — Send API 并行研究架构
节点：decompose_plan / research_branch / global_verify / global_summary / format_answer
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

    # 解析锚点分析
    anchor_analysis = ""
    if "## 锚点分析" in content:
        anchor_section = content.split("## 锚点分析")[1]
        anchor_analysis = anchor_section.split("## 子问题列表")[0].strip() if "## 子问题列表" in anchor_section else anchor_section.strip()

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

    print(f"[DecomposePlan] 锚点分析:\n{anchor_analysis}")
    print(f"[DecomposePlan] 新增 {len(filtered)} 个子问题，总计 {len(all_questions)} 个")
    for sq in all_questions:
        print(f"  [{sq['status']}][{sq['priority']}] Q{sq['id']}: {sq['question']}")

    return {
        "sub_questions": all_questions,
        "anchor_analysis": anchor_analysis,
    }


# ==================== 节点 2：研究分支（并行，由 Send API 调度） ====================

def research_branch(state: AgentState) -> dict:
    """研究分支节点 — 由 Send API 并行调度，使用 LLM function calling 选择搜索工具"""
    sq = state.get("current_branch_question", {})
    if not sq:
        print(f"[ResearchBranch] 无子问题，跳过")
        return {"evidence_pool": [], "completed_question_ids": []}

    q_id = sq["id"]
    query = sq["question"]

    print(f"\n[ResearchBranch] 处理 Q{q_id} [{sq.get('priority', '中')}]: {query}")

    llm = _get_llm(temperature=0.1)

    # ===== 阶段1：LLM 选择搜索工具并执行（Function Calling） =====
    search_tools = [bocha_search, serper_search, baike_search]
    tools_by_name = {t.name: t for t in search_tools}
    llm_with_search = llm.bind_tools(search_tools)

    search_prompt = RESEARCH_SEARCH_PROMPT.format(
        sub_question=query,
        purpose=sq.get("purpose", ""),
        original_question=state["original_question"],
    )

    search_results_parts = []
    for attempt in range(MAX_SEARCH_RETRIES):
        try:
            response = llm_with_search.invoke([HumanMessage(content=search_prompt)])
            if response.tool_calls:
                for tc in response.tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc["args"]
                    print(f"  [Search] LLM选择 {tool_name}({tool_args})")
                    try:
                        result = tools_by_name[tool_name].invoke(tool_args)
                        search_results_parts.append(result)
                    except Exception as e:
                        print(f"  [Search] {tool_name} 执行失败: {e}")
            else:
                print(f"  [Search] LLM未选择工具，fallback到auto_search")
                result = auto_search(query)
                search_results_parts.append(result)
            break
        except Exception as e:
            if attempt == MAX_SEARCH_RETRIES - 1:
                print(f"  [Search] 重试耗尽: {e}")
                search_results_parts.append(f"[搜索失败] {query}: {e}")

    if not search_results_parts:
        search_results_parts.append(auto_search(query))

    search_results = "\n\n".join(search_results_parts)
    print(f"\n  [SearchResults]\n{search_results}\n")

    # 深读高价值页面（百科类已返回完整内容，跳过）
    is_baike_only = all("百度百科" in p for p in search_results_parts)
    deep_content = "" if is_baike_only else _deep_read_promising_urls(search_results, max_reads=2)
    if deep_content:
        search_results += "\n\n--- 以下为高价值页面的完整内容 ---\n\n" + deep_content
        print(f"\n  [DeepRead] 已补充 {deep_content.count('[URL内容]')} 个页面的完整内容\n")

    # ===== 阶段2：LLM 反思 + 可选百科验证（Function Calling） =====
    evidence_text = _evidence_summary(state.get("evidence_pool", []))
    llm_with_baike = llm.bind_tools([baike_search])

    reflect_prompt = RESEARCH_REFLECT_PROMPT.format(
        sub_question=query,
        purpose=sq.get("purpose", ""),
        original_question=state["original_question"],
        evidence_summary=evidence_text,
        search_results=search_results[:12000],
    )

    response = llm_with_baike.invoke([HumanMessage(content=reflect_prompt)])
    reflection = response.content.strip()

    # 执行反思阶段的百科验证工具调用
    baike_supplement = ""
    if response.tool_calls:
        baike_parts = []
        for tc in response.tool_calls[:MAX_BAIKE_VERIFY]:
            entity = tc["args"].get("entity", "")
            print(f"  [BaikeVerify] LLM请求验证: {entity}")
            try:
                result = baike_search.invoke(tc["args"])
                if "未找到" not in result and "查询异常" not in result:
                    baike_parts.append(f"百度百科验证 [{entity}]:\n{result[:5000]}")
            except Exception as e:
                print(f"  [BaikeVerify] 失败: {e}")
        if baike_parts:
            baike_supplement = "\n\n--- 百度百科验证补充 ---\n\n" + "\n\n".join(baike_parts)
            print(f"  [BaikeVerify] 已补充 {len(baike_parts)} 个实体的百科信息")

    print(f"[ResearchBranch] Q{q_id} 反思完成")

    # ===== 阶段3：证据提取 =====
    evidence_prompt = RESEARCH_EVIDENCE_PROMPT.format(
        sub_question=query,
        reflection=reflection[:6000],
        baike_supplement=baike_supplement[:4000] if baike_supplement else "",
    )

    response = llm.invoke([HumanMessage(content=evidence_prompt)])
    content = response.content.strip()

    # 解析证据陈述和可靠性
    statement = ""
    reliability = "low"

    if "证据陈述：" in content or "证据陈述:" in content:
        statement = content.split("证据陈述：")[-1].split("证据陈述:")[-1].split("\n")[0].strip()
    else:
        for line in content.split("\n"):
            line = line.strip()
            if line and len(line) > 5 and "可靠性" not in line:
                statement = line
                break

    if "可靠性：" in content or "可靠性:" in content:
        rel_text = content.split("可靠性：")[-1].split("可靠性:")[-1].strip().split("\n")[0].lower()
        if "high" in rel_text or "高" in rel_text:
            reliability = "high"
        elif "medium" in rel_text or "中" in rel_text:
            reliability = "medium"

    if not statement:
        statement = f"关于Q{q_id}的搜索未获得有效信息"

    # 构造证据（使用 q_id 作为 evidence id 基础，避免并行冲突）
    source_urls = re.findall(r'https?://[^\s\)）\]]+', search_results[:5000])[:3]

    new_evidence = Evidence(
        id=q_id * 10,
        source_question_id=q_id,
        statement=statement,
        source_urls=source_urls,
        reliability=reliability,
    )

    print(f"[ResearchBranch] Q{q_id} → E{new_evidence['id']}: {statement}")
    print(f"[ResearchBranch] 可靠性: {reliability}")

    return {
        "evidence_pool": [new_evidence],
        "completed_question_ids": [q_id],
    }


# ==================== 节点 3：全局验证（GoT — 推理链评估） ====================

def global_verify(state: AgentState) -> dict:
    """全局验证节点 — 评估推理链完整性（取代刚性覆盖率百分比）"""
    loop = state.get("loop_count", 0) + 1
    print(f"\n{'='*60}")
    print(f"[GlobalVerify] 推理链评估（第 {loop} 轮）")
    print(f"{'='*60}")

    # 先更新子问题状态
    completed_set = set(state.get("completed_question_ids", []))
    sub_questions = list(state.get("sub_questions", []))
    for sq in sub_questions:
        if sq["id"] in completed_set and sq["status"] == "pending":
            sq["status"] = "done"

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
    formatted = response.content.strip()

    print(f"[FormatAnswer] 最终输出: {formatted}")

    return {"formatted_answer": formatted}

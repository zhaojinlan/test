# -*- coding: utf-8 -*-
"""
研究子图（Research Subgraph）— 用于封装单个子问题的固定研究流程。

该子图会被主图通过 Send API 并行调度（并发粒度：子问题级）。
为了进一步缩短单个子问题的耗时，子图内部对多搜索引擎请求与 DeepRead 采用线程并发。
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from agents.prompts import RESEARCH_SEARCH_PROMPT, RESEARCH_REFLECT_PROMPT, RESEARCH_EVIDENCE_PROMPT
from config.settings import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL_NAME,
    MAX_SEARCH_RETRIES,
    MAX_BAIKE_VERIFY,
)
from graph.state import Evidence
from tools.search import baike_search, bocha_search, fetch_url_content, serper_search


class ResearchSubgraphState(TypedDict, total=False):
    original_question: str
    evidence_pool: list
    current_branch_question: dict
    completed_question_ids: list
    search_results: str
    reflection: str
    baike_supplement: str


def _get_llm(temperature: float = 0.1) -> ChatOpenAI:
    return ChatOpenAI(
        model=LLM_MODEL_NAME,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        temperature=temperature,
    )


def _evidence_summary(evidence_pool: list) -> str:
    if not evidence_pool:
        return "（暂无证据）"
    return "\n".join(
        [f"  [E{e['id']}] (可靠性:{e['reliability']}) {e['statement']}" for e in evidence_pool]
    )


_HIGH_VALUE_URL_PATTERNS = [
    "baike.baidu.com",
    "baike.sogou.com",
]


def _extract_urls(raw_results: str) -> List[str]:
    return re.findall(r"https?://[^\s\)）\]]+", raw_results)


def _deep_read_parallel(raw_results: str, max_reads: int = 2) -> str:
    urls = _extract_urls(raw_results)
    picked: List[str] = []
    for url in urls:
        if len(picked) >= max_reads:
            break
        if any(p in url for p in _HIGH_VALUE_URL_PATTERNS):
            picked.append(url)
    if not picked:
        return ""

    parts: List[str] = []
    with ThreadPoolExecutor(max_workers=len(picked)) as ex:
        futs = [ex.submit(fetch_url_content, url, 15000) for url in picked]
        for fut in as_completed(futs):
            try:
                c = fut.result()
                if "[URL读取失败]" not in c and "[URL内容]" in c and len(c) > 100:
                    parts.append(c)
            except Exception:
                continue
    return "\n\n".join(parts)


def _search_parallel(state: ResearchSubgraphState) -> dict:
    sq = state.get("current_branch_question", {})
    q_id = sq.get("id", "?")
    query = sq.get("question", "")
    engine = (sq.get("search_engine") or "both").lower()

    if not query:
        return {"search_results": ""}

    print(f"  [Q{q_id}/Search] 开始搜索 (engine={engine})")
    llm = _get_llm(temperature=0.1)
    search_tools = [bocha_search, serper_search, baike_search]
    tools_by_name = {t.name: t for t in search_tools}
    llm_with_search = llm.bind_tools(search_tools)

    search_prompt = RESEARCH_SEARCH_PROMPT.format(
        sub_question=query,
        purpose=sq.get("purpose", ""),
        original_question=state.get("original_question", ""),
    )

    tool_calls = []
    for attempt in range(MAX_SEARCH_RETRIES):
        try:
            response = llm_with_search.invoke([HumanMessage(content=search_prompt)])
            tool_calls = getattr(response, "tool_calls", None) or []
            break
        except Exception:
            if attempt == MAX_SEARCH_RETRIES - 1:
                tool_calls = []

    calls = []
    if tool_calls:
        for tc in tool_calls:
            tool_name = tc.get("name")
            tool_args = tc.get("args") or {}
            if tool_name in tools_by_name:
                calls.append((tool_name, tools_by_name[tool_name].invoke, tool_args))
                print(f"  [Q{q_id}/Search] LLM选择 {tool_name}({tool_args})")
    else:
        print(f"  [Q{q_id}/Search] LLM未选择工具，fallback到 engine={engine}")
        if engine == "baike":
            calls = [("baike", baike_search.invoke, {"entity": query})]
        elif engine == "bocha":
            calls = [("bocha", bocha_search.invoke, {"query": query})]
        elif engine == "serper":
            calls = [("serper", serper_search.invoke, {"query": query})]
        else:
            calls = [
                ("bocha", bocha_search.invoke, {"query": query}),
                ("serper", serper_search.invoke, {"query": query}),
            ]

    results: List[str] = []
    max_workers = max(1, min(len(calls), 4))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(fn, args) for _, fn, args in calls]
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                results.append(f"[搜索失败] {query}: {e}")

    print(f"  [Q{q_id}/Search] 搜索完成，获取 {len(results)} 组结果")
    search_results = "\n\n".join(results)
    deep_content = "" if engine == "baike" else _deep_read_parallel(search_results, max_reads=2)
    if deep_content:
        search_results += "\n\n--- 以下为高价值页面的完整内容 ---\n\n" + deep_content
        url_count = deep_content.count("[URL内容]")
        print(f"  [Q{q_id}/DeepRead] 补充 {url_count} 个高价值页面")

    return {"search_results": search_results}


def _reflect(state: ResearchSubgraphState) -> dict:
    sq = state.get("current_branch_question", {})
    q_id = sq.get("id", "?")
    query = sq.get("question", "")
    print(f"  [Q{q_id}/Reflect] 开始反思...")
    llm = _get_llm(temperature=0.1)
    llm_with_baike = llm.bind_tools([baike_search])

    reflect_prompt = RESEARCH_REFLECT_PROMPT.format(
        sub_question=query,
        purpose=sq.get("purpose", ""),
        original_question=state.get("original_question", ""),
        evidence_summary=_evidence_summary(state.get("evidence_pool", [])),
        search_results=(state.get("search_results", "") or "")[:12000],
    )

    response = llm_with_baike.invoke([HumanMessage(content=reflect_prompt)])
    reflection = response.content.strip()

    baike_supplement = ""
    if getattr(response, "tool_calls", None):
        baike_parts = []
        for tc in response.tool_calls[:MAX_BAIKE_VERIFY]:
            entity = tc["args"].get("entity", "")
            print(f"  [Q{q_id}/BaikeVerify] 验证实体: {entity}")
            try:
                result = baike_search.invoke(tc["args"])
                if "未找到" not in result and "查询异常" not in result:
                    baike_parts.append(f"百度百科验证 [{entity}]:\n{result[:5000]}")
            except Exception:
                continue
        if baike_parts:
            baike_supplement = "\n\n--- 百度百科验证补充 ---\n\n" + "\n\n".join(baike_parts)
            print(f"  [Q{q_id}/BaikeVerify] 补充 {len(baike_parts)} 个实体的百科信息")
    else:
        print(f"  [Q{q_id}/Reflect] 反思完成，未触发百科验证")

    return {"reflection": reflection, "baike_supplement": baike_supplement}


def _extract_evidence(state: ResearchSubgraphState) -> dict:
    sq = state.get("current_branch_question", {})
    q_id = int(sq.get("id", 0) or 0)
    query = sq.get("question", "")
    print(f"  [Q{q_id}/Evidence] 提取证据...")

    llm = _get_llm(temperature=0.1)
    evidence_prompt = RESEARCH_EVIDENCE_PROMPT.format(
        sub_question=query,
        reflection=(state.get("reflection", "") or "")[:6000],
        baike_supplement=(state.get("baike_supplement", "") or "")[:4000],
    )

    response = llm.invoke([HumanMessage(content=evidence_prompt)])
    content = response.content.strip()

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

    source_urls = _extract_urls((state.get("search_results", "") or "")[:5000])[:3]

    new_evidence = Evidence(
        id=q_id * 10,
        source_question_id=q_id,
        statement=statement,
        source_urls=source_urls,
        reliability=reliability,
    )
    print(f"  [Q{q_id}/Evidence] → E{new_evidence['id']} ({reliability}): {statement[:80]}")

    return {
        "evidence_pool": [new_evidence],
        "completed_question_ids": [q_id],
    }


def compile_research_subgraph():
    workflow = StateGraph(ResearchSubgraphState)
    workflow.add_node("search", _search_parallel)
    workflow.add_node("reflect", _reflect)
    workflow.add_node("evidence", _extract_evidence)

    workflow.set_entry_point("search")
    workflow.add_edge("search", "reflect")
    workflow.add_edge("reflect", "evidence")
    workflow.add_edge("evidence", END)

    return workflow.compile()

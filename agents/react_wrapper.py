"""
AutoGen GroupChat 多智能体协作封装
研究员、分析师、验证员在同一对话中交互，实时交叉验证。
GroupChatManager 作为协调者自动选择下一位发言者。
"""

import re
import logging
import difflib
from typing import Optional, Annotated
from autogen import ConversableAgent, GroupChat, GroupChatManager
from config.settings import get_autogen_llm_config, MAX_GROUP_CHAT_ROUNDS
from tools.bocha_search import BochaSearchTool
from tools.serper_search import SerperSearchTool
from tools.code_executor import get_code_executor
from agents.prompts import (
    RESEARCH_SYSTEM_PROMPT,
    ANALYSIS_SYSTEM_PROMPT,
    VERIFICATION_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

# 全局搜索工具实例（避免重复创建）
_bocha_tool: BochaSearchTool | None = None
_serper_tool: SerperSearchTool | None = None


def _get_bocha_tool() -> BochaSearchTool:
    global _bocha_tool
    if _bocha_tool is None:
        _bocha_tool = BochaSearchTool()
    return _bocha_tool


def _get_serper_tool() -> SerperSearchTool:
    global _serper_tool
    if _serper_tool is None:
        _serper_tool = SerperSearchTool()
    return _serper_tool


def _normalize_query(query: str) -> str:
    """归一化查询用于去重比较：小写、去引号、去多余空格。"""
    q = query.lower().strip()
    q = q.replace('"', '').replace("'", '')
    q = re.sub(r'\s+', ' ', q)
    return q


def _is_duplicate_query(query: str, cache: dict, threshold: float = 0.85) -> Optional[str]:
    """
    检查查询是否与缓存中的某个查询重复（精确匹配或模糊匹配）。
    返回匹配到的缓存 key，或 None。
    """
    norm = _normalize_query(query)
    if norm in cache:
        return norm
    for cached_norm in cache:
        ratio = difflib.SequenceMatcher(None, norm, cached_norm).ratio()
        if ratio >= threshold:
            return cached_norm
    return None


class GroupChatOrchestrator:
    """
    使用 AutoGen GroupChat 实现的多智能体协作系统。

    架构：
    - user_proxy（无 LLM）：发起对话 + 执行工具调用
    - researcher（LLM）：广度搜索，收集关键线索
    - analyst（LLM）：深度分析，建立逻辑链
    - verifier（LLM）：事实核查，交叉验证
    - GroupChatManager（LLM）：自动选择下一位发言者

    所有代理共享同一对话，可实时质疑、补充、修正彼此的发现。
    """

    MAX_OBS_CHARS = 6000
    DEDUP_SIMILARITY_THRESHOLD = 0.85

    def __init__(self, max_rounds: int = MAX_GROUP_CHAT_ROUNDS):
        self.max_rounds = max_rounds
        self._search_cache: dict[str, str] = {}
        self.bocha_tool = _get_bocha_tool()
        self.serper_tool = _get_serper_tool()

        llm_config = get_autogen_llm_config()

        # ---- user_proxy: 无 LLM，发起对话 + 执行工具 ----
        self.user_proxy = ConversableAgent(
            name="user_proxy",
            human_input_mode="NEVER",
            llm_config=False,
            is_termination_msg=lambda msg: (
                msg.get("content") is not None
                and "TERMINATE" in msg.get("content", "")
            ),
            default_auto_reply="请继续讨论。",
            max_consecutive_auto_reply=1,
        )

        # ---- researcher: 广度搜索（CoT）----
        self.researcher = ConversableAgent(
            name="researcher",
            system_message=RESEARCH_SYSTEM_PROMPT,
            llm_config=llm_config,
            human_input_mode="NEVER",
        )

        # ---- analyst: 深度分析（ToT）----
        self.analyst = ConversableAgent(
            name="analyst",
            system_message=ANALYSIS_SYSTEM_PROMPT,
            llm_config=llm_config,
            human_input_mode="NEVER",
        )

        # ---- verifier: 事实核查（CoT）----
        self.verifier = ConversableAgent(
            name="verifier",
            system_message=VERIFICATION_SYSTEM_PROMPT,
            llm_config=llm_config,
            human_input_mode="NEVER",
        )

        # ---- 注册工具到所有 LLM 代理 ----
        self._register_tools()

        # ---- GroupChat: 所有代理在同一对话中交互 ----
        self.groupchat = GroupChat(
            agents=[self.user_proxy, self.researcher, self.analyst, self.verifier],
            messages=[],
            max_round=self.max_rounds,
            speaker_selection_method="auto",
            allow_repeat_speaker=False,
        )

        # ---- GroupChatManager: 协调者（自动选择发言者）----
        self.manager = GroupChatManager(
            groupchat=self.groupchat,
            llm_config=llm_config,
            is_termination_msg=lambda msg: (
                msg.get("content") is not None
                and "TERMINATE" in msg.get("content", "")
            ),
        )

    # ------------------------------------------------------------------
    # 工具注册
    # ------------------------------------------------------------------
    def _register_tools(self):
        """将工具注册到所有 LLM 代理（LLM 端）和 user_proxy（执行端）。"""
        llm_agents = [self.researcher, self.analyst, self.verifier]

        # ---- search_google ----
        def search_google(
            query: Annotated[str, "Search query, preferably in English. Google operators like \"exact\" and site: are supported."],
        ) -> str:
            return self._execute_search("google", query)

        # ---- search_bocha ----
        def search_bocha(
            query: Annotated[str, "Natural language search query, preferably in Chinese. No search operators."],
        ) -> str:
            return self._execute_search("bocha", query)

        # ---- run_code ----
        def run_code(
            code: Annotated[str, "Python code to execute. Must use print() to output results."],
        ) -> str:
            return self._execute_code(code)

        # 在 user_proxy 上注册执行
        self.user_proxy.register_for_execution(name="search_google")(search_google)
        self.user_proxy.register_for_execution(name="search_bocha")(search_bocha)
        self.user_proxy.register_for_execution(name="run_code")(run_code)

        # 在每个 LLM 代理上注册 LLM 端
        for agent in llm_agents:
            agent.register_for_llm(
                name="search_google",
                description=(
                    "Google search engine for international/overseas content. "
                    "Supports Google advanced operators: \"exact match\", site:, intitle:, etc. "
                    "Use English queries for best results. "
                    "Use for: foreign people, English papers, international organizations, "
                    "overseas events, foreign companies."
                ),
            )(search_google)

            agent.register_for_llm(
                name="search_bocha",
                description=(
                    "Bocha search engine for Chinese domestic content. "
                    "Only supports natural language queries, NO advanced syntax. "
                    "Use Chinese queries for best results. "
                    "Use for: Chinese people, Chinese papers, domestic organizations, "
                    "events in China, Chinese companies."
                ),
            )(search_bocha)

            agent.register_for_llm(
                name="run_code",
                description=(
                    "Execute Python code for math calculations, date arithmetic, "
                    "unit conversions, string processing, etc. "
                    "Use print() to output results. "
                    "Available: math, re, json, datetime, statistics, decimal, "
                    "fractions, collections."
                ),
            )(run_code)

    # ------------------------------------------------------------------
    # 工具执行（内部）
    # ------------------------------------------------------------------
    def _execute_search(self, engine: str, query: str) -> str:
        """执行搜索，包含去重检查和结果截断。"""
        dup_key = _is_duplicate_query(
            query, self._search_cache, self.DEDUP_SIMILARITY_THRESHOLD
        )
        if dup_key is not None:
            print(f"  │ [GroupChat] {engine} [DEDUP] → {query[:80]}")
            cached = self._search_cache[dup_key]
            return (
                f"[DUPLICATE] This query is too similar to a previous search. "
                f"Cached result:\n{cached[:2000]}\n"
                f"Please try a completely different search angle."
            )

        print(f"  │ [GroupChat] {engine} → {query[:100]}")

        if engine == "google":
            result = self.serper_tool.execute(query)
        else:
            result = self.bocha_tool.execute(query)

        norm_key = _normalize_query(query)
        self._search_cache[norm_key] = result

        if len(result) > self.MAX_OBS_CHARS:
            result = result[: self.MAX_OBS_CHARS] + f"\n...[已截断，原始 {len(result)} 字符]"

        return result

    def _execute_code(self, code: str) -> str:
        """执行 Python 代码。"""
        print(f"  │ [GroupChat] code execution")
        executor = get_code_executor()
        result = executor.execute(code)
        if len(result) > self.MAX_OBS_CHARS:
            result = result[: self.MAX_OBS_CHARS]
        print(f"  │ output: {result[:200]}")
        return result

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def run(self, question: str, sub_questions: list, context: str = "") -> str:
        """
        执行 GroupChat 多智能体协作。

        所有代理在同一对话中交互：
        researcher 搜索 → analyst 即时分析 → verifier 即时验证 → 交叉修正

        Args:
            question:      原始问题
            sub_questions:  拆分后的子问题列表
            context:       已有上下文信息

        Returns:
            群组讨论的综合结论
        """
        # 重置搜索缓存和 GroupChat 消息
        self._search_cache = {}
        self.groupchat.messages.clear()

        prompt = self._build_task_prompt(question, sub_questions, context)

        print(f"\n{'═'*70}")
        print(f"  ▶ GroupChat 多智能体协作启动")
        print(f"    参与者: researcher, analyst, verifier")
        print(f"    最大轮次: {self.max_rounds}")
        print(f"    问题: {question[:80]}...")
        print(f"{'═'*70}")

        try:
            chat_result = self.user_proxy.initiate_chat(
                self.manager,
                message=prompt,
            )
            result = self._extract_result(chat_result)
        except Exception as e:
            logger.error(f"[GroupChat] 执行失败: {e}", exc_info=True)
            result = f"GroupChat 执行失败: {e}"

        print(f"\n  ╔═ GroupChat 最终结论")
        print(f"  ║ {result[:300]}")
        print(f"  ╚═")
        print(f"{'═'*70}")

        return result

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _build_task_prompt(
        self, question: str, sub_questions: list, context: str
    ) -> str:
        parts = [
            f"# 原始问题\n{question}\n",
        ]

        if sub_questions:
            parts.append("# 拆分的子问题")
            for i, sq in enumerate(sub_questions, 1):
                content = sq.get("content", sq) if isinstance(sq, dict) else str(sq)
                parts.append(f"  {i}. {content}")
            parts.append("")

        if context:
            parts.append(f"# 已有上下文\n{context}\n")

        parts.append(
            "# 任务要求\n"
            "请三位专家（researcher、analyst、verifier）协作完成以上问题。\n"
            "- researcher 负责搜索关键事实和线索\n"
            "- analyst 负责建立逻辑关系和推理链\n"
            "- verifier 负责验证关键声明的准确性\n"
            "\n"
            "请积极互动：质疑不确定的信息、补充遗漏的线索、修正错误的结论。\n"
            "当团队对答案达成共识后，由最后发言者输出最终结论并在末尾加上 TERMINATE。"
        )
        return "\n".join(parts)

    def _extract_result(self, chat_result) -> str:
        """从 GroupChat 结果中提取最终结论。"""
        # 优先使用 summary
        if chat_result.summary:
            summary = chat_result.summary.replace("TERMINATE", "").strip()
            if summary:
                return summary

        # 回退：遍历 chat_history 找最后一条有实质内容的代理消息
        for msg in reversed(chat_result.chat_history):
            content = msg.get("content", "")
            if not content:
                continue
            if msg.get("role") == "tool":
                continue
            name = msg.get("name", "")
            if name == "user_proxy":
                continue
            content = content.replace("TERMINATE", "").strip()
            if content:
                return content

        return "未能得出结论"

    def extract_evidence_from_history(self) -> list:
        """从 GroupChat 历史中提取证据列表，供 LangGraph 状态使用。"""
        evidence = []
        for msg in self.groupchat.messages:
            name = msg.get("name", "")
            content = msg.get("content", "")
            if not content or name == "user_proxy" or msg.get("role") == "tool":
                continue
            evidence.append({
                "source": name,
                "content": content.replace("TERMINATE", "").strip()[:500],
            })
        return evidence

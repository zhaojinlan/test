"""
AutoGen ConversableAgent + ReAct 封装
内层 ReAct：Thought → Action → Observation 循环
"""

import re
import logging
from typing import Optional, Tuple
from autogen import ConversableAgent
from config.settings import get_autogen_llm_config, MAX_AGENT_STEPS
from tools.bocha_search import BochaSearchTool
from tools.code_executor import get_code_executor

logger = logging.getLogger(__name__)

# 全局搜索工具实例（避免重复创建）
_search_tool: BochaSearchTool | None = None


def _get_search_tool() -> BochaSearchTool:
    global _search_tool
    if _search_tool is None:
        _search_tool = BochaSearchTool()
    return _search_tool


class ReactSubAgent:
    """
    使用 AutoGen ConversableAgent 实现的 ReAct 子代理。

    通过手动驱动 Thought-Action-Observation 循环，
    确保每一步的推理过程显式、可观测。
    """

    MAX_OBS_CHARS = 6000  # 每次 Observation 传回给模型的最大字符数

    def __init__(
        self,
        name: str,
        system_prompt: str,
        max_steps: int = MAX_AGENT_STEPS,
    ):
        self.name = name
        self.max_steps = max_steps
        self.search_tool = _get_search_tool()

        self.agent = ConversableAgent(
            name=name,
            system_message=system_prompt,
            llm_config=get_autogen_llm_config(),
            human_input_mode="NEVER",
            is_termination_msg=lambda _: False,
        )

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def run(self, task: str, context: str = "") -> str:
        """
        执行 ReAct 循环并返回最终结果。

        Args:
            task:    子任务描述
            context: 上下文信息（已有证据等）

        Returns:
            子代理的最终回答
        """
        initial_prompt = self._build_initial_prompt(task, context)
        conversation = [{"role": "user", "content": initial_prompt}]

        print(f"\n{'─'*60}")
        print(f"  ▶ 子代理 [{self.name}] 启动")
        print(f"    任务: {task[:80]}...")
        print(f"{'─'*60}")

        for step in range(1, self.max_steps + 1):
            # ---- Agent 思考 ----
            try:
                response = self.agent.generate_reply(messages=conversation)
            except Exception as e:
                logger.error(f"[{self.name}] LLM 调用失败: {e}")
                conversation = self._trim_conversation(conversation)
                continue

            if response is None:
                logger.warning(f"[{self.name}] 空回复，跳过")
                continue

            if isinstance(response, dict):
                response = response.get("content", str(response))

            conversation.append({"role": "assistant", "content": response})

            # ---- 检查 Final Answer ----
            final = self._extract_final_answer(response)
            if final:
                self._print_final(step, final)
                return final

            # ---- 解析 Action 并执行 ----
            action_type, action_input = self._parse_action(response)
            thought = self._extract_thought(response)

            if action_type == "search" and action_input:
                self._print_step(step, thought, f"search → {action_input[:100]}")
                observation = self.search_tool.execute(action_input)
                obs_truncated = observation[: self.MAX_OBS_CHARS]
                if len(observation) > self.MAX_OBS_CHARS:
                    obs_truncated += f"\n...[已截断，原始 {len(observation)} 字符]"

                conversation.append({
                    "role": "user",
                    "content": f"Observation:\n{obs_truncated}\n\n请继续你的推理。",
                })

            elif action_type == "code" and action_input:
                self._print_step(step, thought, f"code → {action_input[:100]}")
                executor = get_code_executor()
                code_result = executor.execute(action_input)
                obs_truncated = code_result[: self.MAX_OBS_CHARS]
                print(f"  | Code Output: {obs_truncated[:200]}")

                conversation.append({
                    "role": "user",
                    "content": f"Observation (code output):\n{obs_truncated}\n\n请根据计算结果继续推理。",
                })

            else:
                # 没有解析到 Action，提示模型继续
                self._print_step(step, thought, "(无有效 Action)")
                conversation.append({
                    "role": "user",
                    "content": (
                        "未检测到有效的 Action。请严格按照格式输出：\n"
                        "Thought: ...\nAction: search\nAction Input: <查询>\n"
                        "或 Action: code\nAction Input:\n```python\n<代码>\n```\n"
                        "或者输出 Final Answer: <最终结论>"
                    ),
                })

        # ---- 超过最大步数，强制总结 ----
        return self._force_conclusion(task, conversation)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _build_initial_prompt(self, task: str, context: str) -> str:
        parts = [f"请完成以下任务：\n{task}"]
        if context:
            parts.append(f"\n已有上下文信息：\n{context}")
        parts.append("\n请按照你的思维框架开始推理。输出 Thought: 开始。")
        return "\n".join(parts)

    @staticmethod
    def _extract_thought(text: str) -> str:
        m = re.search(r"Thought:\s*(.+?)(?=Action:|Final Answer:|$)", text, re.DOTALL)
        return m.group(1).strip() if m else text[:200]

    @staticmethod
    def _parse_action(text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        解析 Action 类型和内容。
        返回 (action_type, action_input)，其中 action_type 为 'search' 或 'code'。
        """
        # 先检测 Action 类型
        action_match = re.search(r"Action:\s*(search|code)\b", text, re.IGNORECASE)
        if not action_match:
            # 兼容旧格式：没有明确 Action 类型但有 Action Input
            m = re.search(r"Action Input:\s*(.+?)(?=\n\n|Thought:|$)", text, re.DOTALL)
            if m:
                content = m.group(1).strip()
                # 根据内容推断类型：包含代码块标记则为 code
                if "```python" in content or "```py" in content:
                    code = re.sub(r"```(?:python|py)?\s*", "", content)
                    code = code.replace("```", "").strip()
                    return "code", code
                return "search", content
            return None, None

        action_type = action_match.group(1).lower()

        # 提取 Action Input
        after_action = text[action_match.end():]
        m = re.search(r"Action Input:\s*(.+?)(?=\nThought:|\nAction:|\nFinal Answer:|$)", after_action, re.DOTALL)
        if not m:
            return action_type, None

        content = m.group(1).strip()

        # 如果是 code 类型，去掉 markdown 代码块标记
        if action_type == "code":
            content = re.sub(r"```(?:python|py)?\s*", "", content)
            content = content.replace("```", "").strip()

        return action_type, content if content else None

    @staticmethod
    def _extract_final_answer(text: str) -> Optional[str]:
        m = re.search(r"Final Answer:\s*(.+?)$", text, re.DOTALL)
        return m.group(1).strip() if m else None

    def _force_conclusion(self, task: str, conversation: list) -> str:
        """达到最大步数后，强制模型给出结论。"""
        conversation.append({
            "role": "user",
            "content": (
                "你已达到最大推理步数。请根据目前收集到的所有信息，"
                "立即给出最终结论。\n"
                "Final Answer:"
            ),
        })
        try:
            response = self.agent.generate_reply(messages=conversation)
            if isinstance(response, dict):
                response = response.get("content", str(response))
            final = self._extract_final_answer(response) if response else None
            result = final or (response.strip() if response else "未能得出结论")
        except Exception as e:
            logger.error(f"[{self.name}] 强制总结失败: {e}")
            result = "推理过程未能得出明确结论"

        print(f"  ⚠ [{self.name}] 达到最大步数，强制结束")
        print(f"  ✔ 结论: {result[:120]}...")
        return result

    def _trim_conversation(self, conversation: list) -> list:
        """上下文过长时裁剪中间轮次。"""
        if len(conversation) <= 3:
            return conversation
        keep = max(1, len(conversation) // 2)
        trimmed = [conversation[0]] + conversation[-keep:]
        logger.info(f"[{self.name}] 裁剪会话: {len(conversation)} -> {len(trimmed)}")
        return trimmed

    # ------------------------------------------------------------------
    # 打印
    # ------------------------------------------------------------------
    def _print_step(self, step: int, thought: str, action_input: str):
        print(f"\n  ┌─ [{self.name}] Step {step}")
        print(f"  │ Thought : {thought[:150]}")
        print(f"  │ Action  : {action_input[:120]}")
        print(f"  └─")

    def _print_final(self, step: int, answer: str):
        print(f"\n  ┌─ [{self.name}] Step {step} ── Final Answer")
        print(f"  │ {answer[:200]}")
        print(f"  └─")
        print(f"{'─'*60}")

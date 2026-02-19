"""
Serper Google Search 工具 —— 封装 Serper.dev API
用途：英文查询的高质量 Google 搜索结果
"""

import logging
import requests
from config.settings import SERPER_API_KEY, SERPER_BASE_URL, SERPER_DEFAULT_COUNT

logger = logging.getLogger(__name__)


class SerperSearchTool:
    """Serper Google Search 封装，用于英文查询场景。"""

    def __init__(
        self,
        api_key: str = SERPER_API_KEY,
        base_url: str = SERPER_BASE_URL,
        default_count: int = SERPER_DEFAULT_COUNT,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._default_count = default_count

    # ------------------------------------------------------------------
    def execute(self, query: str, count: int | None = None) -> str:
        """
        执行 Google 搜索并返回格式化文本。

        Args:
            query:  搜索关键词 / 自然语言查询
            count:  返回条目数（可选）

        Returns:
            格式化的搜索结果字符串
        """
        if not query or not query.strip():
            return "错误：搜索关键词不能为空"

        headers = {
            "X-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "q": query.strip(),
            "num": count or self._default_count,
        }

        try:
            logger.info(f"[SerperSearch] query={query}")
            resp = requests.post(
                self._base_url, headers=headers, json=payload, timeout=30
            )

            if resp.status_code != 200:
                msg = f"Serper API HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error(msg)
                return msg

            data = resp.json()

            # 提取 organic 结果
            organic = data.get("organic", [])
            if not organic:
                return "未找到相关结果。"

            # 提取 knowledge graph（如果有）
            kg = data.get("knowledgeGraph", {})
            kg_text = ""
            if kg:
                kg_text = self._format_knowledge_graph(kg)

            results_text = self._format(organic)

            if kg_text:
                return f"{kg_text}\n\n{results_text}"
            return results_text

        except requests.Timeout:
            return "搜索请求超时，请稍后重试。"
        except Exception as e:
            msg = f"Serper 搜索执行异常: {e}"
            logger.error(msg)
            return msg

    # ------------------------------------------------------------------
    @staticmethod
    def _format(organic: list) -> str:
        """将 organic 搜索结果列表格式化为可读文本。"""
        parts = []
        for i, item in enumerate(organic, 1):
            parts.append(
                f"【结果 {i}】\n"
                f"  标题: {item.get('title', 'N/A')}\n"
                f"  URL : {item.get('link', 'N/A')}\n"
                f"  摘要: {item.get('snippet', 'N/A')}"
            )
            if item.get("date"):
                parts[-1] += f"\n  时间: {item['date']}"
        return "\n\n".join(parts)

    @staticmethod
    def _format_knowledge_graph(kg: dict) -> str:
        """格式化 Knowledge Graph 信息。"""
        parts = ["【知识图谱】"]
        if kg.get("title"):
            parts.append(f"  名称: {kg['title']}")
        if kg.get("type"):
            parts.append(f"  类型: {kg['type']}")
        if kg.get("description"):
            parts.append(f"  描述: {kg['description']}")
        attrs = kg.get("attributes", {})
        for key, val in attrs.items():
            parts.append(f"  {key}: {val}")
        return "\n".join(parts)

"""
博查搜索工具 —— 封装博查 Web Search API
"""

import logging
import requests
from config.settings import SEARCH_API_KEY, SEARCH_BASE_URL, SEARCH_DEFAULT_COUNT, SEARCH_FRESHNESS

logger = logging.getLogger(__name__)


class BochaSearchTool:
    """博查 Web Search 封装，供 AutoGen 子代理调用。"""

    def __init__(
        self,
        api_key: str = SEARCH_API_KEY,
        base_url: str = SEARCH_BASE_URL,
        default_count: int = SEARCH_DEFAULT_COUNT,
        freshness: str = SEARCH_FRESHNESS,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._default_count = default_count
        self._freshness = freshness

    # ------------------------------------------------------------------
    def execute(self, query: str, count: int | None = None) -> str:
        """
        执行搜索并返回格式化文本。

        Args:
            query:  搜索关键词 / 自然语言查询
            count:  返回条目数（可选）

        Returns:
            格式化的搜索结果字符串
        """
        if not query or not query.strip():
            return "错误：搜索关键词不能为空"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query.strip(),
            "freshness": self._freshness,
            "summary": True,
            "count": count or self._default_count,
        }

        try:
            logger.info(f"[BochaSearch] query={query}")
            resp = requests.post(self._base_url, headers=headers, json=payload, timeout=30)

            if resp.status_code != 200:
                msg = f"搜索API HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error(msg)
                return msg

            data = resp.json()
            if data.get("code") != 200 or not data.get("data"):
                msg = f"搜索API业务错误: {data.get('msg', '未知')}"
                logger.error(msg)
                return msg

            pages = data["data"].get("webPages", {}).get("value", [])
            if not pages:
                return "未找到相关结果。"

            return self._format(pages)

        except requests.Timeout:
            return "搜索请求超时，请稍后重试。"
        except Exception as e:
            msg = f"搜索执行异常: {e}"
            logger.error(msg)
            return msg

    # ------------------------------------------------------------------
    @staticmethod
    def _format(pages: list) -> str:
        """将搜索结果列表格式化为可读文本。"""
        parts = []
        for i, p in enumerate(pages, 1):
            parts.append(
                f"【结果 {i}】\n"
                f"  标题: {p.get('name', 'N/A')}\n"
                f"  URL : {p.get('url', 'N/A')}\n"
                f"  摘要: {p.get('summary', p.get('snippet', 'N/A'))}\n"
                f"  来源: {p.get('siteName', 'N/A')}\n"
                f"  时间: {p.get('dateLastCrawled', 'N/A')}"
            )
        return "\n\n".join(parts)

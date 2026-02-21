# -*- coding: utf-8 -*-
"""
搜索引擎工具封装 — 支持博查（中文）和 Serper/Google（国际）
所有工具均为 LangChain @tool 装饰器格式，支持 function calling。
"""
import re
import html
import requests
from langchain_core.tools import tool

from config.settings import (
    BOCHA_API_KEY, BOCHA_BASE_URL, BOCHA_DEFAULT_COUNT,
    SERPER_API_KEY, SERPER_BASE_URL, SERPER_DEFAULT_NUM,
    BAIKE_API_KEY, BAIKE_LIST_URL, BAIKE_CONTENT_URL,
)


# ==================== 底层 API 调用 ====================

def _call_bocha(query: str, count: int = BOCHA_DEFAULT_COUNT) -> dict:
    """博查搜索底层调用"""
    headers = {
        "Authorization": f"Bearer {BOCHA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "summary": False,
        "freshness": "noLimit",
        "count": count,
    }
    resp = requests.post(BOCHA_BASE_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 200:
        return {"success": False, "results": [],
                "error": f"Bocha API code {data.get('code')}: {data.get('msg')}"}

    web_pages = data.get("data", {}).get("webPages", {}).get("value", [])
    results = []
    for item in web_pages:
        results.append({
            "title": item.get("name", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", ""),
            "summary": item.get("summary", ""),
            "site_name": item.get("siteName", ""),
            "date": item.get("datePublished", ""),
        })
    return {"success": True, "results": results, "error": None}


def _call_serper(query: str, num: int = SERPER_DEFAULT_NUM, gl: str = "us", hl: str = "en") -> dict:
    """Serper (Google) 搜索底层调用"""
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "q": query,
        "num": num,
        "gl": gl,
        "hl": hl,
    }
    resp = requests.post(SERPER_BASE_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results = []
    # organic 结果
    for item in data.get("organic", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "summary": item.get("snippet", ""),
            "site_name": item.get("source", ""),
            "date": item.get("date", ""),
        })
    # knowledgeGraph 如果存在，作为首条结果
    kg = data.get("knowledgeGraph")
    if kg:
        kg_desc = kg.get("description", "")
        kg_title = kg.get("title", "")
        if kg_desc:
            results.insert(0, {
                "title": f"[Knowledge Graph] {kg_title}",
                "url": kg.get("descriptionLink", ""),
                "snippet": kg_desc,
                "summary": kg_desc,
                "site_name": "Google Knowledge Graph",
                "date": "",
            })
    return {"success": True, "results": results, "error": None}


def _format_results(raw: dict, query: str, engine: str) -> str:
    """将搜索结果格式化为可读文本"""
    if not raw["success"]:
        return f"[{engine}搜索失败] 查询: {query}, 错误: {raw.get('error', '未知')}"

    if not raw["results"]:
        return f"[{engine}] 查询 '{query}' 无结果"

    lines = [f"[{engine}] 查询: {query} — 共 {len(raw['results'])} 条结果\n"]
    for i, r in enumerate(raw["results"], 1):
        text = r.get("summary") or r.get("snippet") or ""
        lines.append(f"{i}. {r['title']}\n   {text[:600]}\n   来源: {r['site_name']} | {r['url']}")
    return "\n".join(lines)


# ==================== LangChain Tools (function calling) ====================

@tool
def bocha_search(query: str) -> str:
    """搜索中文互联网内容（支持自然语言句子）。适用于：中文问题、中国相关话题、中文百科/论坛/新闻。
    输入应为完整的中文自然语言句子（如"哪个开源硬件项目的灵感来源于元胞自动机？"），返回搜索结果摘要。"""
    try:
        raw = _call_bocha(query)
        return _format_results(raw, query, "博查")
    except Exception as e:
        return f"[博查搜索异常] {query}: {e}"


@tool
def serper_search(query: str) -> str:
    """搜索国际互联网内容（Google）。适用于：英文关键词、国际学术/技术话题、维基百科、GitHub等。
    输入搜索查询字符串，返回搜索结果摘要。"""
    try:
        raw = _call_serper(query)
        return _format_results(raw, query, "Google")
    except Exception as e:
        return f"[Google搜索异常] {query}: {e}"


# ==================== 百度百科精确查询 ====================

def _call_baike_list(lemma_title: str, top_k: int = 5) -> dict:
    """百度百科词条列表查询 — 根据词条名获取义项列表"""
    headers = {
        "Authorization": f"Bearer {BAIKE_API_KEY}",
        "Content-Type": "application/json",
    }
    params = {
        "lemma_title": lemma_title,
        "top_k": top_k,
    }
    resp = requests.get(BAIKE_LIST_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") and str(data["code"]) != "0":
        return {"success": False, "results": [],
                "error": f"Baike list API: {data.get('message', '未知错误')}"}

    result_list = data.get("result", [])
    if not result_list:
        return {"success": True, "results": [], "error": None}

    results = []
    for item in result_list:
        results.append({
            "lemma_id": item.get("lemma_id"),
            "title": item.get("lemma_title", ""),
            "desc": item.get("lemma_desc", ""),
            "url": item.get("url", ""),
        })
    return {"success": True, "results": results, "error": None}


def _call_baike_content(search_key: str) -> dict:
    """百度百科词条内容查询 — 根据词条名获取完整内容"""
    headers = {
        "Authorization": f"Bearer {BAIKE_API_KEY}",
        "Content-Type": "application/json",
    }
    params = {
        "search_type": "lemmaTitle",
        "search_key": search_key,
    }
    resp = requests.get(BAIKE_CONTENT_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") and str(data["code"]) != "0":
        return {"success": False, "content": "",
                "error": f"Baike content API: {data.get('message', '未知错误')}"}

    result = data.get("result", {})
    if not result:
        return {"success": True, "content": "", "error": None}

    return {"success": True, "content": result, "error": None}


def _format_baike_content(raw: dict) -> str:
    """格式化百度百科内容为可读文本"""
    content = raw.get("content", "")
    if not content:
        return ""

    # content 可能是 dict 或 str
    if isinstance(content, dict):
        # 尝试提取常见字段
        parts = []
        for key, val in content.items():
            if isinstance(val, str) and val.strip():
                parts.append(f"{key}: {val[:2000]}")
            elif isinstance(val, list):
                for item in val[:20]:
                    if isinstance(item, dict):
                        parts.append(str(item))
                    elif isinstance(item, str):
                        parts.append(item)
        return "\n".join(parts)
    elif isinstance(content, str):
        return content[:8000]
    return str(content)[:8000]


@tool
def baike_search(entity: str) -> str:
    """精确查询百度百科词条内容。适用于：查询特定实体（人名、作品名、公司名等）的详细信息。
    输入应为准确的实体名称（如"猫眼三姐妹"、"刘德华"），返回百科词条的完整内容。"""
    try:
        # 第一步：获取义项列表
        list_raw = _call_baike_list(entity, top_k=3)

        lines = [f"[百度百科] 查询: {entity}\n"]

        if list_raw["success"] and list_raw["results"]:
            lines.append(f"找到 {len(list_raw['results'])} 个义项：")
            for i, item in enumerate(list_raw["results"], 1):
                lines.append(f"  {i}. {item['title']} — {item['desc']}")
                lines.append(f"     URL: {item['url']}")
            lines.append("")

        # 第二步：获取词条内容
        content_raw = _call_baike_content(entity)
        if content_raw["success"] and content_raw["content"]:
            formatted = _format_baike_content(content_raw)
            if formatted:
                lines.append("--- 词条内容 ---")
                lines.append(formatted)
            else:
                lines.append("（词条内容为空）")
        elif not list_raw.get("results"):
            lines.append(f"未找到 '{entity}' 的百科词条")

        return "\n".join(lines)
    except Exception as e:
        return f"[百度百科查询异常] {entity}: {e}"


# ==================== URL 内容读取 ====================

# 百科类网站的正文容器模式（正则），按优先级排列
_ARTICLE_BODY_PATTERNS = [
    # 搜狗百科
    r'<div[^>]*class="[^"]*lemma[_-]?content[^"]*"[^>]*>(.*?)</div>\s*(?=<div[^>]*class="[^"]*(?:sidebar|related|footer))',
    # 百度百科
    r'<div[^>]*class="[^"]*main-content[^"]*"[^>]*>(.*)',
    r'<div[^>]*class="[^"]*lemmaWgt-lemmaSummary[^"]*"[^>]*>(.*)',
    # 维基百科
    r'<div[^>]*class="[^"]*mw-parser-output[^"]*"[^>]*>(.*)',
    # 通用：<article> 标签
    r'<article[^>]*>(.*?)</article>',
    # 通用：id/class 含 content/article/main 的大 div
    r'<div[^>]*(?:id|class)="[^"]*(?:article|content|main-body|entry)[^"]*"[^>]*>(.*)',
]


def _strip_html(raw_html: str) -> str:
    """从 HTML 中提取纯文本 — 增强版，移除更多噪声元素"""
    # 第1步：移除不可见内容标签（含内容一起删除）
    noise_tags = r'script|style|noscript|nav|header|footer|aside|svg|template|iframe|form'
    text = re.sub(
        rf'<({noise_tags})[^>]*>.*?</\1>',
        '', raw_html, flags=re.DOTALL | re.IGNORECASE,
    )
    # 第2步：移除常见噪声 div（class/id 含 sidebar, recommend, comment, ad, breadcrumb 等）
    noise_div_pat = r'(?:sidebar|recommend|comment|ad-|advert|breadcrumb|related-|share-|copyright|disclaimer)'
    text = re.sub(
        rf'<div[^>]*(?:class|id)="[^"]*{noise_div_pat}[^"]*"[^>]*>.*?</div>',
        '', text, flags=re.DOTALL | re.IGNORECASE,
    )
    # 第3步：移除所有 HTML 标签
    text = re.sub(r'<[^>]+>', ' ', text)
    # 第4步：解码 HTML 实体
    text = html.unescape(text)
    # 第5步：合并连续空白
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()


def _extract_article_body(raw_html: str) -> str:
    """尝试提取页面主体内容区域（百科/wiki类页面优化）。
    成功则返回主体区域 HTML，失败则返回空字符串（交由 _strip_html 处理全页）。"""
    for pattern in _ARTICLE_BODY_PATTERNS:
        m = re.search(pattern, raw_html, flags=re.DOTALL | re.IGNORECASE)
        if m:
            body = m.group(1) if m.lastindex else m.group(0)
            # 确保提取到的内容有足够的实际文本（排除空 div）
            plain_check = re.sub(r'<[^>]+>', '', body).strip()
            if len(plain_check) > 200:
                return body
    return ""


def fetch_url_content(url: str, max_chars: int = 15000) -> str:
    """读取指定 URL 的页面内容，返回纯文本（截断到 max_chars）。
    对百科/wiki 类页面会先尝试提取正文区域，减少导航噪声。"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.encoding = resp.apparent_encoding or "utf-8"
        raw = resp.text

        # 优先尝试提取主体内容区域
        article_html = _extract_article_body(raw)
        if article_html:
            text = _strip_html(article_html)
        else:
            text = _strip_html(raw)

        if len(text) > max_chars:
            text = text[:max_chars] + "\n...[内容截断]"

        return f"[URL内容] {url}\n{text}" if text else f"[URL内容] {url}: 页面内容为空"
    except Exception as e:
        return f"[URL读取失败] {url}: {e}"


# ==================== 工具列表（供 LLM bind_tools 使用） ====================

ALL_SEARCH_TOOLS = [bocha_search, serper_search]


def _has_chinese(text: str) -> bool:
    """判断文本是否包含中文字符"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def auto_search(query: str) -> str:
    """根据查询语言自动选择搜索引擎，返回格式化结果文本。
    中文查询 → 博查优先; 英文查询 → Serper 优先。"""
    if _has_chinese(query):
        try:
            raw = _call_bocha(query)
            if raw["success"] and raw["results"]:
                return _format_results(raw, query, "博查")
        except Exception:
            pass
        # 博查失败则降级到 Serper
        try:
            raw = _call_serper(query, hl="zh-CN", gl="cn")
            return _format_results(raw, query, "Google")
        except Exception as e:
            return f"[搜索全部失败] {query}: {e}"
    else:
        try:
            raw = _call_serper(query)
            if raw["success"] and raw["results"]:
                return _format_results(raw, query, "Google")
        except Exception:
            pass
        # Serper 失败则降级到博查
        try:
            raw = _call_bocha(query)
            return _format_results(raw, query, "博查")
        except Exception as e:
            return f"[搜索全部失败] {query}: {e}"

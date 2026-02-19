"""
轻量 OpenAI-compatible LLM 调用封装（供 LangGraph 节点使用）
"""

from openai import OpenAI
from config.settings import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
    return _client


def call_llm(
    user_message: str,
    system_message: str = "",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    调用 LLM 并返回文本回复。

    Args:
        user_message:  用户 prompt
        system_message: system prompt（可选）
        temperature:   覆盖默认温度
        max_tokens:    覆盖默认 max_tokens

    Returns:
        模型回复的纯文本
    """
    client = _get_client()
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": user_message})

    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature if temperature is not None else LLM_TEMPERATURE,
        max_tokens=max_tokens or LLM_MAX_TOKENS,
    )
    return resp.choices[0].message.content.strip()

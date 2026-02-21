# -*- coding: utf-8 -*-
"""
答案后处理工具 — 使用 LLM 进行格式归一化
避免死板的正则，让大模型来理解格式要求
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from config.settings import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME


NORMALIZE_PROMPT = """你是一个答案标准化工具。请对给定的答案进行以下标准化处理，然后只输出处理后的结果。

原始答案：{raw_answer}
题目：{question}

标准化规则：
1. 转小写（仅英文部分）
2. 去除首尾空格
3. 如果是数值答案，转为整数（去掉小数点后的部分）
4. 如果答案包含多个实体，用英文逗号加空格分隔（除非题目另有要求）
5. 去除多余的标点、引号、括号等装饰符号
6. 不要添加任何解释，只输出标准化后的答案本身
7. 如果题目中明确声明了格式要求（如"格式形如：xxx"），则严格按该格式输出，不做大小写转换

请直接输出标准化后的答案："""


def normalize_answer(raw_answer: str, question: str = "") -> str:
    """
    使用 LLM 对答案进行格式归一化。
    
    Args:
        raw_answer: 原始答案文本
        question: 原始问题（用于判断格式要求）
    
    Returns:
        标准化后的答案
    """
    if not raw_answer or not raw_answer.strip():
        return ""

    llm = ChatOpenAI(
        model=LLM_MODEL_NAME,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        temperature=0.0,
    )

    prompt = NORMALIZE_PROMPT.format(
        raw_answer=raw_answer,
        question=question,
    )

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        result = response.content.strip()
        return result
    except Exception as e:
        print(f"[Normalize] LLM 归一化失败: {e}，使用基础处理")
        return raw_answer.strip()

# -*- coding: utf-8 -*-
"""
答案后处理工具 — 使用 LLM 进行格式归一化
避免死板的正则，让大模型来理解格式要求
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from config.settings import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME


NORMALIZE_PROMPT = """你是一个答案标准化与格式对齐工具。你的目标是：优先遵循题目中明确给出的输出格式；如果题目没有明确格式要求，再按通用标准化规则处理。最终只输出处理后的答案本身，不要输出任何分析过程。

原始答案：{raw_answer}
题目：{question}

请按“思维树”方式在脑中完成以下决策与处理（不要在输出中展示这些步骤）：

第一步：判断题目是否给出了“明确的输出格式要求”。满足任一情况都视为“给出了格式要求”：
1) 题目出现类似“格式形如：…/格式为：…/输出格式：…/按…格式输出/结果写成…/用…分隔/保留…位小数/以…开头/以…结尾/输出为JSON/输出为表格/输出为A,B,C”等强约束描述。
2) 题目给出了可直接照抄的模板、示例输出（如“例如：xxx”并且明确要求按示例格式）。
3) 题目要求固定符号、固定单位、固定分隔符、固定括号/引号样式、固定大小写、固定顺序等。

分支A（如果题目给出了明确格式要求）：
- 先抽取题目中的格式约束（模板、分隔符、顺序、大小写、单位、是否要括号/引号等）。
- 将“原始答案”改写为严格符合该格式的输出。
- 除非题目格式要求里明确要求大小写转换，否则不要擅自做英文全小写。

分支B（如果题目没有给出明确格式要求）：
执行下面的通用标准化规则：
1. 英文需要转小写。专有名词、人名、地名除外
2. 去除首尾空格
3. 如果是数值答案，转为整数（去掉小数点后的部分）
4. 如果答案包含多个实体，用英文逗号加空格分隔
5. 去除多余的标点、引号、括号等装饰符号
6. 不要添加任何解释，只输出标准化后的答案本身

输出要求：
- 只输出最终答案（单行优先），不要输出任何解释、步骤、标签或多余文本。
"""


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

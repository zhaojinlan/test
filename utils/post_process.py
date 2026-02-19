"""
答案后处理模块
- 转小写
- 去除首尾空格
- 数值题均为整数
- 多实体逗号/分号后接空格
"""

import re


def post_process_answer(raw: str) -> str:
    """
    对最终答案进行标准化后处理。

    Args:
        raw: 原始答案字符串

    Returns:
        标准化后的答案
    """
    if not raw:
        return ""

    answer = raw.strip()

    # 如果答案纯数字（可能带正负号），转整数字符串
    numeric = answer.replace(",", "").replace(" ", "")
    if re.match(r"^[+-]?\d+(\.\d+)?$", numeric):
        try:
            answer = str(int(float(numeric)))
            return answer
        except ValueError:
            pass

    # 规范化逗号 / 分号后的空格
    answer = re.sub(r",\s*", ", ", answer)
    answer = re.sub(r";\s*", "; ", answer)

    # 转小写
    answer = answer.lower()

    # 再次去除首尾空格
    answer = answer.strip()

    return answer

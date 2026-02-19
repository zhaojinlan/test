"""
安全代码执行器 —— 轻量沙箱
用途：数学计算、字符串处理、日期运算等
安全机制：AST 白名单 + 受限 builtins + stdout 捕获 + 超时
"""

import ast
import io
import math
import re
import json
import statistics
import traceback
import threading
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, date
from typing import Dict, Any, Tuple
from decimal import Decimal
from fractions import Fraction
from collections import Counter, defaultdict


# =====================================================================
# 允许导入的模块白名单
# =====================================================================
ALLOWED_IMPORTS = {
    "math", "re", "json", "statistics",
    "datetime", "decimal", "fractions",
    "collections", "itertools", "functools", "operator",
    "string", "textwrap", "unicodedata",
}

# 禁止调用的危险函数
BLOCKED_FUNCTIONS = {"exec", "eval", "__import__", "compile", "globals", "locals",
                     "getattr", "setattr", "delattr", "open", "input", "breakpoint"}

# 允许的 builtins（移除危险函数）
_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bin": bin,
    "bool": bool, "chr": chr, "complex": complex,
    "dict": dict, "divmod": divmod, "enumerate": enumerate,
    "filter": filter, "float": float, "format": format,
    "frozenset": frozenset, "hash": hash, "hex": hex,
    "int": int, "isinstance": isinstance, "issubclass": issubclass,
    "iter": iter, "len": len, "list": list, "map": map,
    "max": max, "min": min, "next": next, "oct": oct,
    "ord": ord, "pow": pow, "print": print, "range": range,
    "repr": repr, "reversed": reversed, "round": round,
    "set": set, "slice": slice, "sorted": sorted,
    "str": str, "sum": sum, "tuple": tuple, "type": type,
    "zip": zip,
    "True": True, "False": False, "None": None,
}


class CodeExecutor:
    """
    安全的 Python 代码执行器。

    - AST 静态分析：只允许白名单模块 import，阻止危险函数调用
    - 受限全局变量：移除 open/exec/eval/__import__ 等
    - stdout 捕获：返回 print 输出
    - 超时保护：默认 10 秒
    """

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def execute(self, code: str) -> str:
        """
        执行代码并返回结果字符串。

        成功返回 stdout 输出（若为空则返回最后一个表达式的值）。
        失败返回错误信息。
        """
        # 1. 安全检查
        is_safe, err = self._check_safety(code)
        if not is_safe:
            return f"[安全检查失败] {err}"

        # 2. 带超时执行
        result = {"output": "", "error": ""}

        def _run():
            try:
                stdout_buf = io.StringIO()
                stderr_buf = io.StringIO()

                # 构建受限执行环境
                safe_globals = {"__builtins__": _SAFE_BUILTINS.copy()}
                # 预注入常用模块
                safe_globals.update({
                    "math": math,
                    "re": re,
                    "json": json,
                    "statistics": statistics,
                    "datetime": datetime,
                    "timedelta": timedelta,
                    "date": date,
                    "Decimal": Decimal,
                    "Fraction": Fraction,
                    "Counter": Counter,
                    "defaultdict": defaultdict,
                })

                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    exec(compile(code, "<agent_code>", "exec"), safe_globals)

                output = stdout_buf.getvalue().strip()
                err_output = stderr_buf.getvalue().strip()

                if output:
                    result["output"] = output
                elif err_output:
                    result["output"] = err_output
                else:
                    # 如果没有 print 输出，尝试获取最后一个表达式的值
                    last_val = self._eval_last_expr(code, safe_globals)
                    result["output"] = str(last_val) if last_val is not None else "(无输出)"

            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}"

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=self.timeout)

        if thread.is_alive():
            return f"[超时] 代码执行超过 {self.timeout} 秒限制"

        if result["error"]:
            return f"[执行错误] {result['error']}"

        return result["output"]

    # ------------------------------------------------------------------
    # AST 安全检查
    # ------------------------------------------------------------------
    def _check_safety(self, code: str) -> Tuple[bool, str]:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {e}"

        for node in ast.walk(tree):
            # 检查 import
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
                    if mod not in ALLOWED_IMPORTS:
                        return False, f"不允许导入: {alias.name}"

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod = node.module.split(".")[0]
                    if mod not in ALLOWED_IMPORTS:
                        return False, f"不允许导入: {node.module}"

            # 检查危险函数调用
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in BLOCKED_FUNCTIONS:
                        return False, f"不允许调用: {node.func.id}"
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in ("system", "popen", "remove", "rmdir",
                                           "unlink", "rename", "makedirs"):
                        return False, f"不允许调用: {node.func.attr}"

        return True, ""

    # ------------------------------------------------------------------
    # 辅助：获取最后一个表达式的值
    # ------------------------------------------------------------------
    @staticmethod
    def _eval_last_expr(code: str, globals_dict: dict):
        """如果代码最后一行是表达式，返回其值"""
        try:
            tree = ast.parse(code)
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                last_expr = ast.Expression(body=tree.body[-1].value)
                ast.fix_missing_locations(last_expr)
                return eval(compile(last_expr, "<agent_code>", "eval"), globals_dict)
        except Exception:
            pass
        return None


# 单例
_executor: CodeExecutor | None = None


def get_code_executor() -> CodeExecutor:
    global _executor
    if _executor is None:
        _executor = CodeExecutor(timeout=10)
    return _executor

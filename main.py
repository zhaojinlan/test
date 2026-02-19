"""
多智能体推理系统 —— 主入口
架构：LangGraph Supervisor（外层 ReAct）+ AutoGen ConversableAgent（内层 ReAct）
"""

import os
import sys
import logging
import traceback

# 日志文件路径（在任何 import 之前就确定）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(_SCRIPT_DIR, "run.log")


# ------------------------------------------------------------------
# TeeStream：同时写入控制台和日志文件
# ------------------------------------------------------------------
class TeeStream:
    def __init__(self, console, log_file):
        self.console = console
        self.log_file = log_file

    def write(self, text):
        try:
            self.console.write(text)
        except Exception:
            pass
        try:
            self.log_file.write(text)
            self.log_file.flush()
        except Exception:
            pass

    def flush(self):
        try:
            self.console.flush()
        except Exception:
            pass
        try:
            self.log_file.flush()
        except Exception:
            pass


def _init_tee():
    """在最早期就把 stdout/stderr 导出到日志文件"""
    log_fh = open(LOG_FILE, "w", encoding="utf-8")
    sys.stdout = TeeStream(sys.__stdout__, log_fh)
    sys.stderr = TeeStream(sys.__stderr__, log_fh)


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(name)-25s  %(levelname)-7s  %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("autogen").setLevel(logging.WARNING)


def run_question(question: str) -> str:
    """
    对单个问题执行完整的多智能体推理流程。

    Args:
        question: 待回答的问题文本

    Returns:
        最终答案字符串
    """
    # 延迟导入，确保 TeeStream 已生效
    from graph.state import create_initial_state
    from graph.supervisor import build_supervisor_graph
    from config.settings import MAX_SUPERVISOR_ITERATIONS

    print("\n" + "█" * 70)
    print("█  多智能体推理系统")
    print("█  LangGraph Supervisor + AutoGen ReAct Sub-Agents")
    print("█" * 70)
    print(f"\n问题：\n{question}\n")

    # 构建图
    graph = build_supervisor_graph()

    # 初始状态
    initial_state = create_initial_state(
        question=question,
        max_iterations=MAX_SUPERVISOR_ITERATIONS,
    )

    # 执行
    try:
        final_state = graph.invoke(initial_state)
    except Exception as e:
        print(f"\n✖ 系统执行出错: {e}")
        traceback.print_exc()
        return f"执行失败: {e}"

    final_answer = final_state.get("final_answer", "未能生成答案")

    # ---- 打印摘要 ----
    print("\n" + "█" * 70)
    print("█  执行完毕")
    print("█" * 70)
    print(f"\n最终答案: {final_answer}")
    print(f"\n系统统计:")
    print(f"  Supervisor 迭代次数 : {final_state.get('iteration_count', 0)}")
    print(f"  收集证据条数        : {len(final_state.get('evidence_pool', []))}")
    print(f"  子问题数            : {len(final_state.get('sub_questions', []))}")

    trace = final_state.get("reasoning_trace", [])
    if trace:
        print(f"\n推理轨迹（共 {len(trace)} 步）:")
        for t in trace:
            print(f"  · {t[:120]}")

    return final_answer


def main():
    # 1. 最先开启日志文件
    _init_tee()

    # 2. 配置 logging
    setup_logging("INFO")

    print("=" * 70)
    print("  系统启动 …")
    print("=" * 70)

    # 3. 测试问题
    test_question = (
        "一位欧洲学者的某项开源硬件项目，其灵感源于一个著名的元胞自动机，"
        "该项目的一个早期物理设计从四边形框架演变为更稳固的三角形结构。"
        "这位在机械工程某一分支领域深耕的学者，从大学教职岗位上引退后，"
        "继续领导一个与该项目相关的商业实体。该实体在21世纪10年代中期"
        "停止了在其欧洲本土的主要交易，但其在一个亚洲国家的业务得以延续。"
        "这个商业实体的英文名称是什么？要求格式形如：Alibaba Group Limited。"
    )

    try:
        answer = run_question(test_question)
    except Exception as e:
        print(f"\n✖ 顶层异常: {e}")
        traceback.print_exc()
        answer = f"失败: {e}"

    print("\n" + "=" * 70)
    print(f"  >>> 最终答案: {answer}")
    print("=" * 70 + "\n")

    return answer


if __name__ == "__main__":
    main()

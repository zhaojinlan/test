# -*- coding: utf-8 -*-
"""
多智能体推理系统入口
架构：证据池架构 — DecomposePlan / SearchReflect / LocalSummary / GlobalVerify / GlobalSummary
"""
import sys
import os
import time
import traceback

# 确保项目根目录在 path 中
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _PROJECT_DIR)

# 日志文件路径
LOG_FILE = os.path.join(_PROJECT_DIR, "run_log.txt")


class TeeWriter:
    """同时写入控制台和日志文件"""
    def __init__(self, log_path):
        self._original = sys.stdout
        self._log = open(log_path, "w", encoding="utf-8")

    def write(self, text):
        self._original.write(text)
        self._log.write(text)
        self._log.flush()

    def flush(self):
        self._original.flush()
        self._log.flush()

    def close(self):
        self._log.close()


from config.settings import RECURSION_LIMIT
from graph.state import AgentState
from graph.supervisor import compile_graph
from utils.answer_formatter import normalize_answer


def run_question(question: str) -> str:
    """
    运行完整的多智能体推理流程。
    
    Args:
        question: 需要回答的问题
        
    Returns:
        最终格式化后的答案
    """
    print("\n" + "=" * 70)
    print("多智能体推理系统（证据池架构）启动")
    print("=" * 70)
    print(f"问题: {question}")
    print("=" * 70)

    start_time = time.time()

    # 初始化状态
    initial_state: AgentState = {
        "original_question": question,
        "sub_questions": [],
        "anchor_analysis": "",
        "evidence_pool": [],
        "current_branch_question": {},
        "completed_question_ids": [],
        "reasoning_chain": "",
        "is_sufficient": False,
        "loop_count": 0,
        "force_passed": False,
        "final_answer": "",
        "formatted_answer": "",
    }

    # 编译并运行图
    graph = compile_graph()

    final_state = graph.invoke(
        initial_state,
        {"recursion_limit": RECURSION_LIMIT},
    )

    elapsed = time.time() - start_time

    # 获取格式化答案
    raw_answer = final_state.get("formatted_answer", "") or final_state.get("final_answer", "")

    # LLM 归一化
    normalized = normalize_answer(raw_answer, question)

    # 打印结果
    print("\n" + "=" * 70)
    print("推理完成")
    print("=" * 70)
    print(f"原始问题: {question}")
    print(f"原始答案: {raw_answer}")
    print(f"标准化答案: {normalized}")
    print(f"耗时: {elapsed:.1f}s")
    print(f"循环次数: {final_state.get('loop_count', 0)}")
    print(f"证据池大小: {len(final_state.get('evidence_pool', []))}")
    print(f"推理链充分: {'是' if final_state.get('is_sufficient', False) else '否'}")

    # 打印证据池
    evidence_pool = final_state.get("evidence_pool", [])
    if evidence_pool:
        print(f"\n证据池 ({len(evidence_pool)} 条):")
        for e in evidence_pool:
            print(f"  [E{e['id']}] ({e['reliability']}) {e['statement'][:80]}")

    # 打印子问题摘要
    sub_questions = final_state.get("sub_questions", [])
    if sub_questions:
        print(f"\n子问题 ({len(sub_questions)} 个):")
        for sq in sub_questions:
            icon = {"done": "✓", "pending": "○"}.get(sq["status"], "?")
            print(f"  [{icon}][{sq['priority']}] Q{sq['id']}: {sq['question'][:70]}")

    print("=" * 70)

    return normalized


def main():
    """测试入口"""
    # 启用 TeeWriter，同时输出到控制台和日志文件
    tee = TeeWriter(LOG_FILE)
    sys.stdout = tee

    try:
        test_question = """ 
        一位研究流星的天文学家，曾对一场发生在每年夏末、以高速流星著称的天文现象的尘埃带做出过预测。他还提出，一颗在本世纪初被发现的小行星，可能是一颗约五个世纪前被东亚天文学家记录的彗星的残骸。这颗小行星本身是另一场大型流星雨的母体，而这场流星雨与前述的夏末流星雨同属北半球三大周期性流星雨，并以一个现已废弃的星座命名。当这场发生在年初的流星雨出现时，可以通过哪种常见的设备探测到其流星体燃烧时产生的电离现象？请回答设备英文名。    

        """

        answer = run_question(test_question)
        print(f"\n最终答案: {answer}")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        traceback.print_exc()
    finally:
        sys.stdout = tee._original
        tee.close()
        print(f"日志已保存到: {LOG_FILE}")


if __name__ == "__main__":
    main()

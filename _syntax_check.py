# -*- coding: utf-8 -*-
import sys, os, py_compile, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_syntax_log.txt")

files = [
    "config/settings.py",
    "tools/search.py",
    "agents/prompts.py",
    "graph/state.py",
    "graph/research_subgraph.py",
    "graph/supervisor.py",
    "utils/answer_formatter.py",
    "main.py",
]

with open(LOG, "w", encoding="utf-8") as f:
    all_ok = True
    for fp in files:
        try:
            py_compile.compile(fp, doraise=True)
            f.write(f"[OK] {fp}\n")
        except py_compile.PyCompileError as e:
            f.write(f"[FAIL] {fp}: {e}\n")
            all_ok = False

    # Also try actual imports
    f.write("\n=== Import Test ===\n")
    try:
        from config.settings import LLM_MODEL_NAME, SERPER_API_KEY
        f.write(f"[OK] config.settings: model={LLM_MODEL_NAME}, serper_key={SERPER_API_KEY[:8]}...\n")
    except Exception as e:
        f.write(f"[FAIL] config.settings: {e}\n")
        all_ok = False

    try:
        from tools.search import bocha_search, serper_search, auto_search, ALL_SEARCH_TOOLS
        f.write(f"[OK] tools.search: {len(ALL_SEARCH_TOOLS)} tools\n")
        f.write(f"     bocha_search.name={bocha_search.name}\n")
        f.write(f"     serper_search.name={serper_search.name}\n")
    except Exception as e:
        f.write(f"[FAIL] tools.search: {e}\n")
        traceback.print_exc(file=f)
        all_ok = False

    try:
        from graph.state import AgentState, SubQuestion, Evidence
        f.write("[OK] graph.state\n")
    except Exception as e:
        f.write(f"[FAIL] graph.state: {e}\n")
        all_ok = False

    try:
        from graph.nodes import decompose_plan, research_branch, global_verify, global_summary, format_answer
        f.write("[OK] graph.nodes: all 5 node functions imported\n")
    except Exception as e:
        f.write(f"[FAIL] graph.nodes: {e}\n")
        traceback.print_exc(file=f)
        all_ok = False

    try:
        from graph.supervisor import compile_graph
        g = compile_graph()
        f.write(f"[OK] graph.supervisor: compiled {type(g).__name__}\n")
    except Exception as e:
        f.write(f"[FAIL] graph.supervisor: {e}\n")
        traceback.print_exc(file=f)
        all_ok = False

    try:
        from utils.answer_formatter import normalize_answer
        f.write("[OK] utils.answer_formatter\n")
    except Exception as e:
        f.write(f"[FAIL] utils.answer_formatter: {e}\n")
        all_ok = False

    f.write(f"\n{'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}\n")

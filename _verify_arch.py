# -*- coding: utf-8 -*-
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_verify_arch_log.txt")
results = []

def check(label, fn):
    try:
        fn()
        results.append(f"[OK] {label}")
    except Exception as e:
        results.append(f"[FAIL] {label}: {e}")
        results.append(traceback.format_exc())

check("config.settings", lambda: __import__("config.settings"))
check("agents.prompts", lambda: __import__("agents.prompts"))
check("graph.state", lambda: __import__("graph.state"))
check("graph.nodes", lambda: __import__("graph.nodes"))

def check_supervisor():
    from graph.supervisor import compile_graph
    g = compile_graph()
    nodes = list(g.get_graph().nodes)
    results.append(f"     Graph nodes: {nodes}")
check("graph.supervisor (compile)", check_supervisor)

def check_prompts():
    from agents.prompts import (DECOMPOSE_PLAN_PROMPT, RESEARCH_REFLECT_PROMPT,
        RESEARCH_EVIDENCE_PROMPT, GLOBAL_VERIFY_PROMPT, GLOBAL_SUMMARY_PROMPT, FORMAT_ANSWER_PROMPT)
    results.append(f"     6 prompts imported OK")
check("prompts import", check_prompts)

def check_nodes():
    from graph.nodes import decompose_plan, research_branch, global_verify, global_summary, format_answer
    results.append(f"     5 node functions imported OK")
check("nodes import", check_nodes)

def check_send():
    from langgraph.types import Send
    results.append(f"     Send API available: {Send}")
check("langgraph Send API", check_send)

with open(LOG, "w", encoding="utf-8") as f:
    for r in results:
        f.write(r + "\n")
    ok = all("[FAIL]" not in r for r in results)
    f.write(f"\n{'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED'}\n")
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")

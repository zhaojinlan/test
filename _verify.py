"""Verify all modified modules can be imported without errors."""
import sys
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = []

# 1. config.settings
try:
    from config.settings import (
        SERPER_API_KEY, SERPER_BASE_URL, SERPER_DEFAULT_COUNT,
        SEARCH_API_KEY, LLM_MODEL, get_autogen_llm_config
    )
    results.append(f"OK  config.settings (model={LLM_MODEL}, serper_key={SERPER_API_KEY[:8]}...)")
except Exception as e:
    results.append(f"FAIL config.settings: {e}")

# 2. tools.serper_search
try:
    from tools.serper_search import SerperSearchTool
    s = SerperSearchTool()
    results.append("OK  tools.serper_search")
except Exception as e:
    results.append(f"FAIL tools.serper_search: {e}")

# 3. tools.bocha_search
try:
    from tools.bocha_search import BochaSearchTool
    results.append("OK  tools.bocha_search")
except Exception as e:
    results.append(f"FAIL tools.bocha_search: {e}")

# 4. tools.code_executor
try:
    from tools.code_executor import get_code_executor
    results.append("OK  tools.code_executor")
except Exception as e:
    results.append(f"FAIL tools.code_executor: {e}")

# 5. utils.llm_client
try:
    from utils.llm_client import call_llm
    results.append("OK  utils.llm_client")
except Exception as e:
    results.append(f"FAIL utils.llm_client: {e}")

# 6. utils.post_process
try:
    from utils.post_process import post_process_answer
    results.append("OK  utils.post_process")
except Exception as e:
    results.append(f"FAIL utils.post_process: {e}")

# 7. graph.state
try:
    from graph.state import SupervisorState, create_initial_state
    results.append("OK  graph.state")
except Exception as e:
    results.append(f"FAIL graph.state: {e}")

# 8. agents.prompts
try:
    from agents.prompts import RESEARCH_SYSTEM_PROMPT, ANALYSIS_SYSTEM_PROMPT, VERIFICATION_SYSTEM_PROMPT
    results.append("OK  agents.prompts")
except Exception as e:
    results.append(f"FAIL agents.prompts: {e}")

# 9. agents.react_wrapper
try:
    from agents.react_wrapper import ReactSubAgent, _has_chinese, _normalize_query, _is_duplicate_query
    results.append("OK  agents.react_wrapper")
    # Test helper functions
    assert _has_chinese("hello") == False
    assert _has_chinese("hello world") == False
    assert _normalize_query('"Hello World"') == "hello world"
    assert _is_duplicate_query("hello world", {"hello world": "cached"}) == "hello world"
    assert _is_duplicate_query("totally different query", {"hello world": "cached"}) is None
    results.append("OK  react_wrapper helper functions passed")
except Exception as e:
    results.append(f"FAIL agents.react_wrapper: {e}")

# 10. graph.nodes
try:
    from graph.nodes import (
        analyze_question, decompose_question, supervisor_decide,
        research_execute, analysis_execute, verify_execute,
        synthesize, format_answer
    )
    results.append("OK  graph.nodes")
except Exception as e:
    results.append(f"FAIL graph.nodes: {e}")

# 11. graph.supervisor
try:
    from graph.supervisor import build_supervisor_graph
    results.append("OK  graph.supervisor")
except Exception as e:
    results.append(f"FAIL graph.supervisor: {e}")

# Write results
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_verify_output.txt")
with open(out_path, "w", encoding="utf-8") as f:
    for r in results:
        f.write(r + "\n")
    f.write("\nDone.\n")

print(f"Results written to {out_path}")
for r in results:
    print(r)

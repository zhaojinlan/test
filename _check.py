import sys, os, traceback
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_check_result.txt")
lines = []

try:
    from config.settings import SERPER_API_KEY, SERPER_BASE_URL, SERPER_DEFAULT_COUNT
    lines.append("OK config.settings (SERPER)")
except Exception:
    lines.append("FAIL config.settings: " + traceback.format_exc())

try:
    from tools.serper_search import SerperSearchTool
    lines.append("OK tools.serper_search")
except Exception:
    lines.append("FAIL tools.serper_search: " + traceback.format_exc())

try:
    from tools.bocha_search import BochaSearchTool
    lines.append("OK tools.bocha_search")
except Exception:
    lines.append("FAIL tools.bocha_search: " + traceback.format_exc())

try:
    from agents.react_wrapper import ReactSubAgent, _has_chinese, _normalize_query, _is_duplicate_query
    lines.append("OK agents.react_wrapper")
    assert _has_chinese("test") == False, "has_chinese failed"
    assert _has_chinese("test") == False, "has_chinese2 failed"
    assert _normalize_query('"Hello World"') == "hello world", "normalize failed"
    dup = _is_duplicate_query("hello world", {"hello world": "cached"})
    assert dup == "hello world", f"dedup exact failed: {dup}"
    miss = _is_duplicate_query("totally different", {"hello world": "cached"})
    assert miss is None, f"dedup miss failed: {miss}"
    lines.append("OK helper function tests passed")
except Exception:
    lines.append("FAIL react_wrapper: " + traceback.format_exc())

try:
    from graph.nodes import format_answer, synthesize, analyze_question
    lines.append("OK graph.nodes")
except Exception:
    lines.append("FAIL graph.nodes: " + traceback.format_exc())

try:
    from graph.supervisor import build_supervisor_graph
    lines.append("OK graph.supervisor")
except Exception:
    lines.append("FAIL graph.supervisor: " + traceback.format_exc())

try:
    from agents.prompts import RESEARCH_SYSTEM_PROMPT
    has_guidance = "site:" in RESEARCH_SYSTEM_PROMPT
    lines.append(f"OK agents.prompts (search_guidance={has_guidance})")
except Exception:
    lines.append("FAIL agents.prompts: " + traceback.format_exc())

with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
    f.write("\nDONE\n")

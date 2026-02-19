import sys, traceback
OUT = r"O:\dataAI\dataAgent\_smoke_result.txt"
sys.path.insert(0, r"O:\dataAI\dataAgent")
lines = []
for mod in ["langgraph","autogen","openai","requests"]:
    try:
        __import__(mod)
        lines.append(f"OK {mod}")
    except Exception as e:
        lines.append(f"FAIL {mod}: {e}")
try:
    from config.settings import LLM_MODEL
    lines.append(f"OK config (model={LLM_MODEL})")
except Exception as e:
    lines.append(f"FAIL config: {traceback.format_exc()}")
try:
    from tools.bocha_search import BochaSearchTool
    lines.append("OK bocha_search")
except Exception as e:
    lines.append(f"FAIL bocha_search: {traceback.format_exc()}")
try:
    from agents.react_wrapper import ReactSubAgent
    lines.append("OK react_wrapper")
except Exception as e:
    lines.append(f"FAIL react_wrapper: {traceback.format_exc()}")
try:
    from graph.supervisor import build_supervisor_graph
    lines.append("OK supervisor")
except Exception as e:
    lines.append(f"FAIL supervisor: {traceback.format_exc()}")
with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

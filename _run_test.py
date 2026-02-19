"""Quick import + smoke test — writes results to _test_output.txt"""
import sys
import os
import traceback

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_output.txt")

with open(out_path, "w", encoding="utf-8") as f:
    # 1. Check imports
    modules_to_check = [
        ("langgraph", "langgraph"),
        ("autogen", "autogen (pyautogen)"),
        ("openai", "openai"),
        ("requests", "requests"),
    ]
    for mod, label in modules_to_check:
        try:
            m = __import__(mod)
            v = getattr(m, "__version__", "?")
            f.write(f"OK  {label} v={v}\n")
        except ImportError as e:
            f.write(f"FAIL {label}: {e}\n")

    f.write("\n--- Project imports ---\n")

    # 2. Check project imports
    try:
        from config.settings import LLM_MODEL, SEARCH_API_KEY, get_autogen_llm_config
        f.write(f"OK  config.settings  (model={LLM_MODEL})\n")
    except Exception as e:
        f.write(f"FAIL config.settings: {e}\n")

    try:
        from tools.bocha_search import BochaSearchTool
        f.write("OK  tools.bocha_search\n")
    except Exception as e:
        f.write(f"FAIL tools.bocha_search: {e}\n")

    try:
        from utils.llm_client import call_llm
        f.write("OK  utils.llm_client\n")
    except Exception as e:
        f.write(f"FAIL utils.llm_client: {e}\n")

    try:
        from utils.post_process import post_process_answer
        f.write("OK  utils.post_process\n")
    except Exception as e:
        f.write(f"FAIL utils.post_process: {e}\n")

    try:
        from graph.state import SupervisorState, create_initial_state
        f.write("OK  graph.state\n")
    except Exception as e:
        f.write(f"FAIL graph.state: {e}\n")

    try:
        from agents.prompts import RESEARCH_SYSTEM_PROMPT
        f.write("OK  agents.prompts\n")
    except Exception as e:
        f.write(f"FAIL agents.prompts: {e}\n")

    try:
        from agents.react_wrapper import ReactSubAgent
        f.write("OK  agents.react_wrapper\n")
    except Exception as e:
        f.write(f"FAIL agents.react_wrapper: {traceback.format_exc()}\n")

    try:
        from graph.nodes import analyze_question, supervisor_decide
        f.write("OK  graph.nodes\n")
    except Exception as e:
        f.write(f"FAIL graph.nodes: {traceback.format_exc()}\n")

    try:
        from graph.supervisor import build_supervisor_graph
        f.write("OK  graph.supervisor\n")
    except Exception as e:
        f.write(f"FAIL graph.supervisor: {traceback.format_exc()}\n")

    f.write("\nDone.\n")

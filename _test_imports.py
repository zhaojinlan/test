# -*- coding: utf-8 -*-
import sys
import traceback

sys.path.insert(0, r"O:\dataAI\dataAgent")
log = open(r"O:\dataAI\dataAgent\_test_log.txt", "w", encoding="utf-8")

try:
    log.write("=== Import Test ===\n")
    
    from config.settings import LLM_MODEL_NAME, BOCHA_API_KEY
    log.write(f"Config OK: model={LLM_MODEL_NAME}\n")
    
    from tools.search import bocha_web_search
    log.write("Search tool OK\n")
    
    from graph.state import SupervisorState, ResearchState
    log.write("State OK\n")
    
    from agents.prompts import SUPERVISOR_THINK_PROMPT
    log.write("Prompts OK\n")
    
    from graph.research_subgraph import build_research_subgraph
    log.write("Research subgraph OK\n")
    
    from graph.supervisor import compile_graph
    log.write("Supervisor graph OK\n")

    from utils.answer_formatter import normalize_answer
    log.write("Answer formatter OK\n")
    
    # Quick search test
    log.write("\n=== Search Test ===\n")
    result = bocha_web_search("RepRap project", count=3)
    log.write(f"Search success: {result['success']}\n")
    log.write(f"Results count: {len(result['results'])}\n")
    if result['results']:
        log.write(f"First result: {result['results'][0]['title']}\n")
    if result.get('error'):
        log.write(f"Error: {result['error']}\n")
    
    # Graph compile test
    log.write("\n=== Graph Compile Test ===\n")
    graph = compile_graph()
    log.write(f"Graph compiled: {type(graph)}\n")
    
    log.write("\n=== ALL TESTS PASSED ===\n")

except Exception as e:
    log.write(f"\nERROR: {e}\n")
    log.write(traceback.format_exc())
finally:
    log.close()

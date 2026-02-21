# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_run_log.txt")
with open(LOG, "w", encoding="utf-8") as f:
    try:
        f.write("1. Starting imports...\n"); f.flush()
        from config.settings import LLM_MODEL_NAME, BOCHA_API_KEY
        f.write(f"2. Config OK: {LLM_MODEL_NAME}\n"); f.flush()
        from tools.search import bocha_web_search
        f.write("3. Search tool OK\n"); f.flush()
        from graph.state import SupervisorState, ResearchState
        f.write("4. State OK\n"); f.flush()
        from graph.research_subgraph import build_research_subgraph
        f.write("5. Research subgraph OK\n"); f.flush()
        from graph.supervisor import compile_graph
        f.write("6. Supervisor graph OK\n"); f.flush()
        # Test search
        r = bocha_web_search("RepRap 3D printer open source", count=3)
        f.write(f"7. Search test: success={r['success']}, count={len(r['results'])}\n"); f.flush()
        if r["error"]:
            f.write(f"   Error: {r['error']}\n"); f.flush()
        for item in r["results"][:2]:
            f.write(f"   - {item['title'][:80]}\n"); f.flush()
        # Compile graph
        g = compile_graph()
        f.write(f"8. Graph compiled: {type(g).__name__}\n"); f.flush()
        f.write("ALL OK\n")
    except Exception as e:
        import traceback
        f.write(f"\nERROR: {e}\n")
        f.write(traceback.format_exc())

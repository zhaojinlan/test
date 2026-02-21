# -*- coding: utf-8 -*-
import sys, os
os.chdir(r"O:\dataAI\dataAgent")
sys.path.insert(0, r"O:\dataAI\dataAgent")
log = r"O:\dataAI\dataAgent\_vcheck.log"
with open(log, "w", encoding="utf-8") as f:
    try:
        import py_compile
        files = [
            "config/settings.py", "graph/state.py", "agents/prompts.py",
            "tools/search.py", "graph/nodes.py", "graph/supervisor.py", "main.py"
        ]
        for fp in files:
            py_compile.compile(fp, doraise=True)
            f.write(f"SYNTAX OK: {fp}\n")
        
        from graph.supervisor import compile_graph
        g = compile_graph()
        nodes = list(g.get_graph().nodes.keys())
        f.write(f"GRAPH OK: {nodes}\n")
        f.write("ALL CHECKS PASSED\n")
    except Exception as e:
        import traceback
        f.write(f"ERROR: {e}\n")
        f.write(traceback.format_exc())

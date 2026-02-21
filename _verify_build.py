# -*- coding: utf-8 -*-
import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_verify.txt")
try:
    from graph.supervisor import compile_graph
    g = compile_graph()
    nodes = list(g.get_graph().nodes.keys())
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"OK: Graph compiled\n")
        f.write(f"Nodes: {nodes}\n")
except Exception as e:
    import traceback
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"ERROR: {e}\n")
        f.write(traceback.format_exc())

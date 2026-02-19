import sys
sys.stdout.reconfigure(encoding='utf-8')

results = []
for mod_name in ['langgraph', 'autogen', 'openai', 'requests']:
    try:
        m = __import__(mod_name)
        v = getattr(m, '__version__', 'no version attr')
        results.append(f"{mod_name}: OK (v={v})")
    except ImportError as e:
        results.append(f"{mod_name}: MISSING ({e})")

for r in results:
    print(r)

with open('_check_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

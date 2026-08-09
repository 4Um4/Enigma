"""
Запуск: python scripts/cycle_detector.py
"""

import json
import sys
from pathlib import Path

def tarjan_scc(graph):
    index_counter = [0]
    stack = []
    lowlink = {}
    index = {}
    on_stack = {}
    result = []

    def strongconnect(node):
        index[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True

        # Идём по рёбрам (зависимостям)
        for successor in graph.get(node, {}).get("imports", []):
            if successor not in graph:
                continue # Внешний модуль (typing, etc.)
            if successor not in index:
                strongconnect(successor)
                lowlink[node] = min(lowlink[node], lowlink[successor])
            elif on_stack.get(successor):
                lowlink[node] = min(lowlink[node], index[successor])

        if lowlink[node] == index[node]:
            component = []
            while True:
                successor = stack.pop()
                on_stack[successor] = False
                component.append(successor)
                if successor == node:
                    break
            result.append(component)

    for node in graph:
        if node not in index:
            strongconnect(node)

    return result

if __name__ == "__main__":
    graph_path = Path("deps_compressed.json")
    if not graph_path.exists():
        print("❌ deps_compressed.json не найден. Запустите scripts/APS.py")
        sys.exit(1)

    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    sccs = tarjan_scc(graph)
    
    # Фильтруем SCC с длиной > 1 (это циклы) или самозависимости
    cycles = [c for c in sccs if len(c) > 1 or (len(c) == 1 and c[0] in graph.get(c[0], {}).get("imports", []))]

    if not cycles:
        print("✅ Циклических зависимостей (back-edges) не найдено. Граф ацикличен.")
    else:
        print(f"🔴 Найдено {len(cycles)} циклических зависимостей (SCC > 1):")
        for i, cycle in enumerate(cycles, 1):
            print(f"\nCycle #{i}:")
            for node in cycle:
                print(f"  - {node}")

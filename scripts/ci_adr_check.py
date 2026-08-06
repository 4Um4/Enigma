# scripts/ci_adr_check.py
"""
path: /project/scripts/ci_adr_check.py
Назначение: CI/CD скрипт для проверки ADR-графа на циклические зависимости.
Выход: code 0 (успех), code 1 (конфликт найден — коммит заблокирован).
Зависимости: app.services.adr_net
"""
import sys
import os
from pathlib import Path

def main():
    # Добавляем корень проекта в path
    _root = Path(__file__).resolve().parents[1]
    _backend = _root / "backend"
    sys.path.insert(0, str(_backend))
    os.chdir(_root)

    from app.services.adr_net.adr_graph import ADRGraphBuilder
    from app.services.adr_net.adr_conflict_detector import ADRConflictDetector

    print("[CI_ADR_CHECK] Building ADR graph...")
    builder = ADRGraphBuilder()
    graph = builder.build()

    if graph.number_of_nodes() == 0:
        print("[CI_ADR_CHECK] ERROR: ADR Graph is empty. Parser failed or files not found.")
        sys.exit(1)

    print(f"[CI_ADR_CHECK] Graph built: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges.")

    print("[CI_ADR_CHECK] Checking for conflicts...")
    detector = ADRConflictDetector(graph)
    results = detector.check_all()
    cycles = results.get("cycles", [])

    if cycles:
        print("[CI_ADR_CHECK] 🔴 FAILED: Cyclic dependencies detected!")
        for cycle in cycles:
            print(f"  - {' -> '.join(cycle)}")
        sys.exit(1)
    else:
        print("[CI_ADR_CHECK] ✅ PASSED: No cyclic dependencies found.")
        sys.exit(0)

if __name__ == "__main__":
    main()
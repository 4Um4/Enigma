# backend/app/services/adr_net/adr_cli.py
"""
path: /project/backend/app/services/adr_net/adr_cli.py
Назначение: CLI для запросов к ADR-Net (Этап 4.4).
Зависимости: argparse, app.services.adr_net.adr_graph, app.services.adr_net.adr_conflict_detector
Основные сущности: CLI entry point
"""
import argparse
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="ENIGMA ADR-Net CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    impact_parser = subparsers.add_parser("impact", help="Что ломается, если я поменяю файл?")
    impact_parser.add_argument("--file", required=True, help="Путь к файлу (например, backend/app/services/tick_orchestrator.py)")

    conflicts_parser = subparsers.add_parser("conflicts", help="Проверить граф на конфликты")

    args = parser.parse_args()

    # Добавляем корень проекта в sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

    from app.services.adr_net.adr_graph import ADRGraphBuilder
    from app.services.adr_net.adr_conflict_detector import ADRConflictDetector

    builder = ADRGraphBuilder()
    graph = builder.build()

    if args.command == "impact":
        impacted = builder.get_impact(args.file)
        if impacted:
            print(f"\n📄 Файл '{args.file}' затрагивает следующие ADR:")
            for adr_id in impacted:
                node_data = graph.nodes[adr_id]
                print(f"  - {adr_id} [{node_data.get('adr_type', 'STD')}]: {node_data.get('title', '')}")
        else:
            print(f"\n✅ Файл '{args.file}' не привязан ни к одному ADR (или ADR не найдены).")

    elif args.command == "conflicts":
        detector = ADRConflictDetector(graph)
        results = detector.check_all()
        
        cycles = results.get("cycles", [])
        if cycles:
            print("\n🔴 ОБНАРУЖЕНЫ ЦИКЛИЧЕСКИЕ ЗАВИСИМОСТИ:")
            for cycle in cycles:
                print(f"  - {' -> '.join(cycle)}")
        else:
            print("\n✅ Циклических зависимостей не обнаружено.")

if __name__ == "__main__":
    main()
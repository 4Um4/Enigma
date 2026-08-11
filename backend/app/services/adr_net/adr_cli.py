# backend/app/services/adr_net/adr_cli.py
"""
path: /project/backend/app/services/adr_net/adr_cli.py
Назначение: CLI для запросов к ADR-Net (Этап 4.4).
Зависимости: argparse, app.services.adr_net.adr_graph, app.services.adr_net.adr_conflict_detector
Основные сущности: CLI entry point
"""
import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="ENIGMA ADR-Net CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    impact_parser = subparsers.add_parser("impact", help="Что ломается, если я поменяю файл?")
    impact_parser.add_argument("--file", required=True, help="Путь к файлу (например, backend/app/services/tick_orchestrator.py)")

    conflicts_parser = subparsers.add_parser("conflicts", help="Проверить граф на конфликты")
    
    visualize_parser = subparsers.add_parser("visualize", help="Сгенерировать Mermaid-граф")
    visualize_parser.add_argument("--output", default="docs/_adr_graph.md", help="Путь к выходному файлу")

    args = parser.parse_args()

    # Добавляем корень проекта в sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

    from app.services.adr_net.adr_graph import ADRGraphBuilder
    from app.services.adr_net.adr_conflict_detector import ADRConflictDetector
    from app.services.adr_net.adr_visualizer import ADRVisualizer

    builder = ADRGraphBuilder()
    graph = builder.build()

    if args.command == "visualize":
        visualizer = ADRVisualizer(graph)
        visualizer.save_mermaid(args.output)
        logger.info(f"✅ Mermaid-граф сохранён в {args.output}")
        return

    if args.command == "impact":
        impacted = builder.get_impact(args.file)
        if impacted:
            logger.info(f"\n📄 Файл '{args.file}' затрагивает следующие ADR:")
            for adr_id in impacted:
                node_data = graph.nodes[adr_id]
                logger.info(f"  - {adr_id} [{node_data.get('adr_type', 'STD')}]: {node_data.get('title', '')}")
        else:
            logger.info(f"\n✅ Файл '{args.file}' не привязан ни к одному ADR (или ADR не найдены).")

    elif args.command == "conflicts":
        detector = ADRConflictDetector(graph)
        results = detector.check_all()
        
        cycles = results.get("cycles", [])
        if cycles:
            logger.warning("\n🔴 ОБНАРУЖЕНЫ ЦИКЛИЧЕСКИЕ ЗАВИСИМОСТИ:")
            for cycle in cycles:
                logger.warning(f"  - {' -> '.join(cycle)}")
        else:
            logger.info("\n✅ Циклических зависимостей не обнаружено.")

if __name__ == "__main__":
    main()
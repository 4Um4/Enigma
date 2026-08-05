# backend/app/services/adr_net/adr_conflict_detector.py
"""
path: /project/backend/app/services/adr_net/adr_conflict_detector.py
Назначение: Детектор циклических зависимостей и конфликтов в ADR-графе (Этап 4.3).
Зависимости: networkx
Основные сущности: ADRConflictDetector
"""
import logging
import networkx as nx
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ADRConflictDetector:
    """Ищет архитектурные конфликты в графе ADR."""

    def __init__(self, graph: nx.MultiDiGraph):
        self.graph = graph

    def detect_cycles(self) -> List[List[str]]:
        """Детектор циклических зависимостей (SUPERSEDES/DEPENDS_ON)."""
        # Упрощаем граф до простого направленного для поиска циклов
        simple_graph = nx.DiGraph()
        for u, v, data in self.graph.edges(data=True):
            if data.get("edge_type") in ["SUPERSEDES", "DEPENDS_ON", "CONFLICTS_WITH"]:
                simple_graph.add_edge(u, v)
        
        cycles = list(nx.simple_cycles(simple_graph))
        if cycles:
            logger.warning(f"[ADR_NET] Detected {len(cycles)} cyclic dependencies!")
        return cycles

    def detect_file_ownership_conflicts(self) -> List[Dict]:
        """Детектор: один файл IMPLEMENTS разными ADR с разными ролями (если будет добавлено)."""
        conflicts = []
        # В текущей модели парсера мы не извлекаем role, поэтому пока заглушка.
        # При добавлении role в ADRNode, здесь можно будет проверить:
        # file -> [ADR1 (IMPLEMENTS), ADR2 (CONSUMES)] — это нормально.
        # file -> [ADR1 (IMPLEMENTS), ADR2 (IMPLEMENTS)] — это конфликт (Double Truth).
        return conflicts

    def check_all(self) -> Dict[str, Any]:
        """Запускает все проверки."""
        return {
            "cycles": self.detect_cycles(),
            "file_ownership_conflicts": self.detect_file_ownership_conflicts()
        }
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
        """Детектор циклических зависимостей."""
        # H-18 FIX: Парсер пока не извлекает SUPERSEDES/DEPENDS_ON, поэтому ищем циклы по всем рёбрам.
        simple_graph = nx.DiGraph()
        for u, v, data in self.graph.edges(data=True):
            simple_graph.add_edge(u, v)
        
        cycles = list(nx.simple_cycles(simple_graph))
        if cycles:
            logger.warning(f"[ADR_NET] Detected {len(cycles)} cyclic dependencies!")
        return cycles

    def detect_file_ownership_conflicts(self) -> List[Dict]:
        """Детектор: один файл IMPLEMENTS разными ADR с разными законами (Double Truth)."""
        conflicts = []
        file_implementers: dict[str, list[str]] = {}
        for u, v, data in self.graph.edges(data=True):
            if data.get("edge_type") == "IMPLEMENTS":
                file_implementers.setdefault(v, []).append(u)
        
        for file_id, adrs in file_implementers.items():
            if len(adrs) > 1:
                # IPT-CLEANUP: Уточнённая логика Double Truth detection.
                # Конфликт = два ADR с противоречащими законами (CONFLICTS_WITH edge)
                # реализуют один файл. Простое разделение разных законов — не конфликт.
                _all_laws = [set(self.graph.nodes[adr].get("laws", [])) for adr in adrs]
                _intersection = set.intersection(*_all_laws) if _all_laws else set()
                _union = set.union(*_all_laws) if _all_laws else set()

                # Пропускаем, если ADR разделяют хотя бы один закон (разные версии)
                if _intersection:
                    continue

                # Пропускаем, если нет явных CONFLICTS_WITH между ADR
                _has_conflict_edge = False
                for i, adr_a in enumerate(adrs):
                    for adr_b in adrs[i+1:]:
                        if self.graph.has_edge(adr_a, adr_b):
                            edge_data = self.graph.get_edge_data(adr_a, adr_b)
                            if any(d.get("edge_type") == "CONFLICTS_WITH" for d in edge_data.values()):
                                _has_conflict_edge = True
                                break
                    if _has_conflict_edge:
                        break

                if _has_conflict_edge:
                    conflicts.append({
                        "file": file_id,
                        "adrs": adrs,
                        "conflict": "File IMPLEMENTS ADRs with explicit CONFLICTS_WITH edge (Double Truth)"
                    })
        return conflicts

    def check_all(self) -> Dict[str, Any]:
        """Запускает все проверки."""
        return {
            "cycles": self.detect_cycles(),
            "file_ownership_conflicts": self.detect_file_ownership_conflicts()
        }
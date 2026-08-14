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
                # H-19 FIX: Если все ADR разделяют хотя бы один закон, это не конфликт (разные версии одного закона)
                _all_laws = [set(self.graph.nodes[adr].get("laws", [])) for adr in adrs]
                _intersection = set.intersection(*_all_laws) if _all_laws else set()
                if not _intersection:
                    conflicts.append({
                        "file": file_id,
                        "adrs": adrs,
                        "conflict": "File IMPLEMENTS ADRs with disjoint laws (Double Truth risk)"
                    })
        return conflicts

    def check_all(self) -> Dict[str, Any]:
        """Запускает все проверки."""
        return {
            "cycles": self.detect_cycles(),
            "file_ownership_conflicts": self.detect_file_ownership_conflicts()
        }
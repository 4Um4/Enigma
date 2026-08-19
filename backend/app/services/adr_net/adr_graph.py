# backend/app/services/adr_net/adr_graph.py
"""
path: /project/backend/app/services/adr_net/adr_graph.py
Назначение: Построение NetworkX MultiDiGraph на основе распарсенных ADR (Этап 4.2).
Зависимости: networkx, app.services.adr_net.adr_parser
Основные сущности: ADRGraphBuilder

Запуск: 
"""
import logging
from pathlib import Path
from typing import List, Dict, Any
import networkx as nx
from app.services.adr_net.adr_parser import run_parser, ADRNode

logger = logging.getLogger(__name__)

class ADRGraphBuilder:
    """Строит направленный граф зависимостей ADR."""

    def __init__(self, audits_dir: str = None, master_index: str = None):
        # Вычисляем корень проекта (на 4 уровня выше: adr_graph.py -> adr_net -> services -> app -> backend -> ROOT)
        _root = Path(__file__).resolve().parents[4]
        self.audits_dir = audits_dir or str(_root / "docs" / "audits")
        self.master_index = master_index or str(_root / "docs" / "ADR (Architecture Decision Records).md")
        self.graph = nx.MultiDiGraph()

    def build(self) -> nx.MultiDiGraph:
        """Парсит данные и строит граф."""
        parsed_data = run_parser(self.audits_dir, self.master_index)
        
        # run_parser может возвращать как {adr_id: node}, так и {"nodes": [...]}
        if isinstance(parsed_data, dict):
            # Если значения — это ADRNode
            if all(isinstance(v, ADRNode) for v in parsed_data.values()):
                nodes = list(parsed_data.values())
            else:
                nodes = parsed_data.get("nodes", [])
        else:
            nodes = []
        
        # 1. Добавляем узлы ADR
        for node in nodes:
            self.graph.add_node(
                node.adr_id,
                node_type="ADR",
                title=node.title,
                adr_type=node.adr_type,
                domain=node.domain,
                laws=node.laws
            )
            
            # Добавляем файлы как отдельные узлы и связи IMPLEMENTS
            for file_path in node.files:
                file_node_id = f"FILE:{file_path}"
                if file_node_id not in self.graph:
                    self.graph.add_node(file_node_id, node_type="FILE", path=file_path)
                self.graph.add_edge(node.adr_id, file_node_id, edge_type="IMPLEMENTS")

            # Добавляем законы (Laws) как отдельные узлы и связи DEFINES
            for law in node.laws:
                law_node_id = f"LAW:{law}"
                if law_node_id not in self.graph:
                    self.graph.add_node(law_node_id, node_type="LAW", name=law)
                self.graph.add_edge(node.adr_id, law_node_id, edge_type="DEFINES")

        logger.info(f"[ADR_NET] Graph built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges.")
        return self.graph

    def get_impact(self, file_path: str) -> List[str]:
        """Возвращает список ADR, которые зависят от указанного файла.
        
        Поддерживает поиск как по полному пути, так и по короткому имени (basename).
        """
        from pathlib import Path
        target_basename = Path(file_path).name
        
        impacted_adrs = []
        # Ищем все узлы-файлы, которые совпадают по имени
        for node in self.graph.nodes:
            if self.graph.nodes[node].get("node_type") == "FILE":
                stored_path = self.graph.nodes[node].get("path", "")
                stored_basename = Path(stored_path).name
                
                if stored_path == file_path or stored_basename == target_basename:
                    # Нашли файл. Ищем все ADR, которые IMPLEMENTS этот файл
                    for predecessor in self.graph.predecessors(node):
                        if self.graph.nodes[predecessor].get("node_type") == "ADR":
                            impacted_adrs.append(predecessor)
                            
        return list(set(impacted_adrs)) # Убираем дубликаты
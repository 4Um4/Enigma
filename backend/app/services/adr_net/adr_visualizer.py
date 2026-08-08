# backend/app/services/adr_net/adr_visualizer.py
"""
path: /project/backend/app/services/adr_net/adr_visualizer.py
Назначение: Генерация Mermaid-визуализации графа ADR (Этап 4.5).
Зависимости: networkx
Основные сущности: ADRVisualizer
"""
import logging
from typing import Any
import networkx as nx

logger = logging.getLogger(__name__)

class ADRVisualizer:
    """Генерирует Mermaid-код из NetworkX графа ADR."""

    def __init__(self, graph: nx.MultiDiGraph):
        self.graph = graph

    def to_mermaid(self) -> str:
        """Конвертирует граф в формат Mermaid (graph TD)."""
        lines = ["graph TD"]
        
        for node_id, data in self.graph.nodes(data=True):
            node_type = data.get("node_type", "UNKNOWN")
            label = ""
            shape = "[[]]" # Default shape
            
            if node_type == "ADR":
                label = f"{node_id}: {data.get('title', '')}"
                shape = '["{label}"]' # Rectangle
            elif node_type == "FILE":
                label = data.get("path", node_id)
                shape = '(("{label}"))' # Circle
            elif node_type == "LAW":
                label = node_id.replace("LAW:", "")
                shape = '{{"{label}"}}' # Hexagon
            else:
                label = node_id
                shape = '["{label}"]'
                
            # Mermaid не любит спецсимволы в ID, заменяем
            safe_id = node_id.replace(":", "_").replace("/", "_").replace("\\", "_").replace(".", "_").replace(" ", "_")
            lines.append(f"    {safe_id}{shape.format(label=label)}")
            
        for u, v, data in self.graph.edges(data=True):
            edge_type = data.get("edge_type", "RELATED_TO")
            safe_u = u.replace(":", "_").replace("/", "_").replace("\\", "_").replace(".", "_")
            safe_v = v.replace(":", "_").replace("/", "_").replace("\\", "_").replace(".", "_")
            lines.append(f'    {safe_u} -->|{edge_type}| {safe_v}')
            
        return "\n".join(lines)

    def save_mermaid(self, output_path: str) -> None:
        """Сохраняет Mermaid-код в файл."""
        mermaid_code = self.to_mermaid()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"```mermaid\n{mermaid_code}\n```\n")
        logger.info(f"[ADR_NET] Mermaid visualization saved to {output_path}")
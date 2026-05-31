"""
path: build_graph.py
Назначение: Генерация ARCHITECTURE_FLOW.md из YAML (Flowchart + Sequence + Micro-details)
Зависимости: PyYAML, os, glob
Основные сущности: ArchitectureGraphBuilder

Запуск: python build_graph.py

TODO:
- [x] Базовая генерация flowchart из YAML
- [x] Поддержка кастомных стилей узлов
"""

import yaml
import os
import glob

class ArchitectureGraphBuilder:
    def __init__(self, yaml_dir="architecture", output_file="docs/ARCHITECTURE_FLOW_GENERATED.md"):
        self.yaml_dir = yaml_dir
        self.output_file = output_file
        self.nodes = {}
        self.edges = []
        self.constraints = []
        self.sequences = []
        
        self.layer_order = ["UI", "Application", "Domain", "Infrastructure"]

    def load_yaml_files(self):
        for filepath in glob.glob(os.path.join(self.yaml_dir, "*.yaml")):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not data:
                    continue
                
                domain = data.get('domain', 'UNKNOWN')
                
                for node_id, node_data in data.get('nodes', {}).items():
                    self.nodes[node_id] = {
                        'domain': domain,
                        'type': node_data.get('type', 'service'),
                        'layer': node_data.get('layer', 'Domain'),
                        'label': node_data.get('label', node_id),
                        'style': node_data.get('style', None)
                    }
                
                for edge in data.get('edges', []):
                    edge['domain'] = domain
                    self.edges.append(edge)
                
                for constraint in data.get('constraints', []):
                    constraint['domain'] = domain
                    self.constraints.append(constraint)
                    
                for seq in data.get('sequences', []):
                    self.sequences.append(seq)

    def _get_mermaid_node_shape(self, node_id, node_data):
        """Строго каноничный синтаксис Mermaid v10+ для форм узлов"""
        label = node_data.get('label', node_id).replace('"', '#quot;')
        ntype = node_data.get('type', 'service')
        
        if ntype == 'database':      return f'{node_id}[("{label}")]'
        if ntype in ('external', 'api'): return f'{node_id}[["{label}"]]'
        if ntype in ('queue', 'event_bus'): return f'{node_id}(("{label}"))'
        if ntype == 'dto':           return f'{node_id}["{label}"]'
        
        return f'{node_id}("{label}")'

    def generate_flowchart(self):
        out = "flowchart TD\n"
        out += "\n    %% === БАЗОВЫЕ СТИЛИ ===\n"
        out += "    classDef ui fill:#e0f7fa,stroke:#006064,stroke-width:2px;\n"
        out += "    classDef application fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px;\n"
        out += "    classDef domain fill:#fff3e0,stroke:#e65100,stroke-width:2px;\n"
        out += "    classDef infrastructure fill:#ffebee,stroke:#b71c1c,stroke-width:2px;\n"
        out += "    classDef forbidden fill:#f66,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5;\n\n"

        current_layer = None
        sorted_nodes = sorted(self.nodes.items(), key=lambda x: (self.layer_order.index(x[1].get('layer', 'Domain')), x[1]['domain']))
        
        custom_styles = []
        
        for node_id, node_data in sorted_nodes:
            layer = node_data.get('layer', 'Domain')
            
            if layer != current_layer:
                if current_layer is not None:
                    out += "    end\n\n"
                current_layer = layer
                out += f"    subgraph {layer.upper()}[{layer} Layer]\n"
                out += f"    direction TB\n"
            
            node_definition = self._get_mermaid_node_shape(node_id, node_data)
            out += f"        {node_definition}:::{layer.lower()}\n"
            
            if node_data.get('style'):
                props = []
                for k, v in node_data['style'].items():
                    v_str = str(v)
                    if k in ['fill', 'stroke'] and not v_str.startswith('#'):
                        v_str = '#' + v_str
                    props.append(f"{k}:{v_str}")
                style_str = ",".join(props)
                custom_styles.append(f"    style {node_id} {style_str};")
        
        out += "    end\n\n"
        
        if custom_styles:
            out += "    %% === КАСТОМНЫЕ СТИЛИ УЗЛОВ ===\n"
            for cs in custom_styles:
                out += cs + "\n"
            out += "\n"

        out += "    %% === ПОТОКИ ДАННЫХ ===\n"
        for edge in self.edges:
            from_node = edge['from']
            to_node = edge['to']
            label = edge.get('label', '')
            
            edge_type = edge.get('edge_type', 'solid')
            if edge_type == 'dotted':
                arrow = "-.->"
            elif edge_type == 'thick':
                arrow = "==>"
            else:
                arrow = "-->"
                
            out += f"    {from_node} {arrow}|\"{label}\"| {to_node}\n"

        out += "\n    %% === АРХИТЕКТУРНЫЕ ЗАПРЕТЫ ===\n"
        for constraint in self.constraints:
            source = constraint['source']
            target = constraint['target']
            rule = constraint['rule']
            out += f"    {source} -.->|\"🚫 {rule}\"| {target}:::forbidden\n"

        return out

    def generate_sequence_diagram(self):
        if not self.sequences:
            return ""
            
        out = "\n## ⏱ Временные Диаграммы (Sequence Diagrams)\n\n"
        
        for seq in self.sequences:
            title = seq.get('title', 'Interaction')
            out += f"### {title}\n\n"
            out += "```mermaid\n"
            out += "sequenceDiagram\n"
            
            for p in seq.get('participants', []):
                out += f"participant {p}\n"
                
            for step in seq.get('steps', []):
                from_p = step['from']
                to_p = step['to']
                msg = step.get('message', '')
                step_type = step.get('type', 'solid')
                
                if step_type == 'dotted':
                    out += f"{from_p}-->>{to_p}: {msg}\n"
                else:
                    out += f"{from_p}->>{to_p}: {msg}\n"
                    
            out += "```\n\n"
            
        return out

    def generate_detail_table(self):
        out = "\n## 📊 Каузальная Карта (Micro-details)\n\n"
        out += "> Детальная логика работы системы: условия срабатывания, привязка к коду и ADR.\n\n"
        
        out += "### Потоки данных (Edges)\n\n"
        out += "| Откуда | Куда | Описание | Условие / Логика | Код | ADR/GAP |\n"
        out += "|--------|------|----------|------------------|-----|---------|\n"
        for edge in self.edges:
            condition = edge.get('condition', '-')
            code_ref = edge.get('code_ref', '-')
            adr_ref = edge.get('adr_ref', '-')
            out += f"| {edge['from']} | {edge['to']} | {edge.get('label', '-')} | {condition} | `{code_ref}` | {adr_ref} |\n"

        out += "\n### Архитектурные запреты (Constraints)\n\n"
        out += "| Источник | Цель | Правило | Код/Документ |\n"
        out += "|----------|------|---------|--------------|\n"
        for constraint in self.constraints:
            code_ref = constraint.get('code_ref', '-')
            out += f"| {constraint['source']} | {constraint['target']} | {constraint['rule']} | `{code_ref}` |\n"

        return out

    def build(self):
        self.load_yaml_files()
        flowchart = self.generate_flowchart()
        sequence = self.generate_sequence_diagram()
        detail_table = self.generate_detail_table()
        
        markdown_content = (
            f"# ARCHITECTURE FLOW (Auto-generated)\n\n"
            f"> Внимание: Этот файл сгенерирован автоматически из `architecture/*.yaml`.\n"
            f"> Не редактируйте его вручную. Изменяйте YAML файлы и запускайте `python build_graph.py`.\n\n"
            f"## 🔗 Топология системы (Flowchart)\n\n"
            f"```mermaid\n{flowchart}```\n"
            f"{sequence}"
            f"{detail_table}"
        )
        
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        print(f"✅ Архитектурный атлас сгенерирован в {self.output_file}")

if __name__ == "__main__":
    builder = ArchitectureGraphBuilder()
    builder.build()
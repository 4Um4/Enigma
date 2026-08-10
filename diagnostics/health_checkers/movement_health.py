"""
path: diagnostics/health_checkers/movement_health.py
Назначение: Строит таблицу движения по каждому NPC за сессию.
            Отслеживает: intent, scene_change (косвенно через state_applied),
            traversal (если появится в логах), финальные координаты.
Зависимости: нет внешних
Основные сущности: NPCMovementState, MovementHealthChecker, MovementHealthReport
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class NPCMovementState:
    """Состояние движения одного NPC за сессию."""

    npc_id: str
    last_intent: str = "?"  # последний Intent из DECISION_HUB
    last_score: float = 0.0
    last_event: str = "?"  # событие, породившее решение
    stress: float = 0.0  # последний stress из STATE_APPLIED
    has_traversal: bool = False  # видели [TRAVERSAL] Start для этого NPC
    traversal_node: str = ""  # целевой узел
    node_not_found: bool = False  # был [MOVEMENT_ENGINE] Узел не найден
    missing_node: str = ""  # имя пропавшего узла
    coord_x: Optional[float] = (
        None  # из последнего DEBUG SPATIAL (если будет отдельный снапшот)
    )
    coord_y: Optional[float] = None
    perception_visible: bool = False  # попал в PERCEPTION_FILTER (близко к игроку)

    def status_icon(self) -> str:
        """Быстрая читаемая оценка для таблицы."""
        if self.node_not_found:
            return "❌ узел не найден"
        if self.has_traversal:
            return f"✅ traversal → {self.traversal_node}"
        if self.last_intent in ("IDLE", "?"):
            return "⏸ IDLE"
        return f"⚠ intent={self.last_intent} без traversal"

    def coords_str(self) -> str:
        if self.coord_x is None:
            return "None"
        return f"x={self.coord_x:.1f} y={self.coord_y:.1f}"


@dataclass
class MovementHealthReport:
    """Итоговый срез движения всех NPC."""

    npcs: Dict[str, NPCMovementState] = field(default_factory=dict)
    spatial_fallback_triggered: bool = False  # location_templates.json недоступен
    editor_json_locations: List[str] = field(
        default_factory=list
    )  # editor JSON найден — реальный граф
    graph_fallback_locations: List[str] = field(
        default_factory=list
    )  # fallback-граф использовался
    total_node_not_found: int = 0

    def get_broken_npcs(self) -> List[str]:
        """NPC у которых есть intent но нет traversal."""
        broken = []
        for npc_id, s in self.npcs.items():
            if (
                s.last_intent not in ("IDLE", "?")
                and not s.has_traversal
            ):
                broken.append(npc_id)
        return broken

    def markdown_table(self) -> str:
        """Рендерит markdown-таблицу для LAST_SESSION.md."""
        if not self.npcs:
            return "_Нет данных по NPC_"
        rows = [
            "| NPC | Intent | Score | Traversal | Координаты | Виден игроку |",
            "|-----|--------|-------|-----------|------------|--------------|",
        ]
        for npc_id, s in sorted(self.npcs.items()):
            traversal = (
                "✅"
                if s.has_traversal
                else ("❌ узел не найден" if s.node_not_found else "⏸")
            )
            visible = "✅" if s.perception_visible else "❌"
            rows.append(
                f"| {npc_id} | {s.last_intent} | {s.last_score:.3f} | "
                f"{traversal} | {s.coords_str()} | {visible} |"
            )
        return "\n".join(rows)


class MovementHealthChecker:
    """
    Накапливает события движения NPC из потока лога.
    """

    def __init__(self) -> None:
        self._report = MovementHealthReport()

    def _get_npc(self, npc_id: str) -> NPCMovementState:
        if npc_id not in self._report.npcs:
            self._report.npcs[npc_id] = NPCMovementState(npc_id=npc_id)
        return self._report.npcs[npc_id]

    def on_decision_hub(
        self, npc_id: str, intent: str, score: float, event: str
    ) -> None:
        npc = self._get_npc(npc_id)
        npc.last_intent = intent
        npc.last_score = score
        npc.last_event = event

    def on_state_applied(self, npc_id: str, stress: float, intent: str) -> None:
        npc = self._get_npc(npc_id)
        npc.stress = stress
        # Уточняем intent если DECISION_HUB не было (fallback)
        if npc.last_intent == "?":
            npc.last_intent = intent

    def on_traversal_start(self, npc_id: str, to_node: str) -> None:
        npc = self._get_npc(npc_id)
        npc.has_traversal = True
        npc.traversal_node = to_node

    def on_node_not_found(self, node: str, npc_id: str, location: str) -> None:
        npc = self._get_npc(npc_id)
        npc.node_not_found = True
        npc.missing_node = node
        self._report.total_node_not_found += 1

    def on_spatial_fallback(self) -> None:
        self._report.spatial_fallback_triggered = True

    def on_editor_json_found(self, location_id: str) -> None:
        """Editor JSON найден — пространственный граф существует, fallback не критичен."""
        if location_id not in self._report.editor_json_locations:
            self._report.editor_json_locations.append(location_id)

    def on_graph_fallback(self, location: str) -> None:
        if location not in self._report.graph_fallback_locations:
            self._report.graph_fallback_locations.append(location)

    def on_trace_snapshot(self, npc_id: str, x: float, y: float) -> None:
        """Обновляет координаты NPC из [TRACE][SNAPSHOT]."""
        npc = self._get_npc(npc_id)
        npc.coord_x = x
        npc.coord_y = y

    def on_engine_received(self, npc_id: str, reason: str) -> None:
        """Фиксирует что MovementEngine получил intent для NPC."""
        npc = self._get_npc(npc_id)
        # reason формата "schedule:sleeping" или "random:wanders_to_bar"
        if ":" in reason:
            npc.last_event = reason

    def on_perception_filter(self, visible_npcs: List[str]) -> None:
        """Отмечаем NPC которые были видны игроку (близко)."""
        for npc_id in visible_npcs:
            self._get_npc(npc_id).perception_visible = True

    def build(self) -> MovementHealthReport:
        return self._report

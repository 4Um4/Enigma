from __future__ import annotations

# backend/app/models/cfrm.py
# Назначение: Доменные структуры Causal Field Reduction Model (CFRM).
# Мир = система локальных причинных пузырей (кластеров).
# Зависимости: stdlib only (Закон 1.2)
# Основные сущности: ClusterID, ClusterDef, ClusterGraph
"""
TODO: В будущем можно расширить CFRM, добавив динамические свойства кластеров (например, "опасный", "социальный центр") и их влияние на NPC внутри. Это позволит более богатое моделирование мира и взаимодействий, сохраняя при этом простоту и эффективность текущей структуры.

"""


from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    FrozenSet,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
)

if TYPE_CHECKING:
    from app.models.npc_state import PerceptualKernel


# ── Типы идентификаторов ─────────────────────────────────────────────
ClusterID = (
    str  # Совпадает с canonical_id макро-узла (напр. "tavern_silver_wolf:main_hall")
)


# ── Пространственная декомпозиция мира ───────────────────────────────


@dataclass(frozen=True)
class ClusterDef:
    """Определение кластера. Не содержит состояния, содержит ТОПОЛОГИЮ.

    Кластер = причинный пузырь. События внутри кластера влияют напрямую.
    Влияние между кластерами проходит через Causal Membrane.

    В текущей реализации: 1 макро-узел (NodeRef) = 1 кластер.
    """

    cluster_id: ClusterID
    # Исходящие границы: узлы соседних кластеров, к которым есть прямой переход
    boundary_cells: FrozenSet[str] = field(default_factory=frozenset)
    # Версия для инкрементального обновления (дрейф кластеров при пересечении NPC границ)
    version: int = 0


@dataclass
class ClusterGraph:
    """Единственная структура мира. НЕ хранит состояние, хранит СВЯЗИ.

    Строится поверх SpatialService на основе макро-зон.
    Обновляется инкрементально (дрейф), только при пересечении NPC границ ячеек.
    """

    clusters: Dict[ClusterID, ClusterDef] = field(default_factory=dict)

    def get_neighbors(self, cluster_id: ClusterID) -> Set[ClusterID]:
        """Возвращает ID соседних кластеров (тех, с кем есть общая граница)."""
        cluster = self.clusters.get(cluster_id)
        if not cluster:
            return set()

        # Граничные точки принадлежат другим кластерам
        neighbor_ids = set()
        for boundary_node_id in cluster.boundary_cells:
            # boundary_node_id имеет формат "location_id:zone_name"
            # Кластер-владелец этой точки — это она сама (т.к. 1 узел = 1 кластер)
            neighbor_ids.add(boundary_node_id)
        return neighbor_ids

    def get_cluster(self, cluster_id: ClusterID) -> ClusterDef | None:
        return self.clusters.get(cluster_id)

    def update_version(self, cluster_id: ClusterID) -> None:
        """Инкремент версии при дрейфе (пересечение NPC границы)."""
        if cluster_id in self.clusters:
            old = self.clusters[cluster_id]
            self.clusters[cluster_id] = ClusterDef(
                cluster_id=old.cluster_id,
                boundary_cells=old.boundary_cells,
                version=old.version + 1,
            )


# ── Оси причинности (CFRM Event Axes) ────────────────────────────────


class CausalAxis(Enum):
    """Три оси потока фактов в EventBuffer.

    Physical: Физика мира (удар, движение, шок)
    Cognitive: Когнитивная обработка (страх, внимание, намерение)
    Social: Социальная физика (слух, доверие, информация)
    """

    PHYSICAL = "physical"
    COGNITIVE = "cognitive"
    SOCIAL = "social"


# ── Временный causal input stream ────────────────────────────────────


@dataclass
class EventBuffer:
    """Временный causal input stream для редукции. НЕ лог, НЕ история.

    Наполняется фактами (EventDTO) в течение тика.
    Опустошается (drain) 3-фазным редюсером в Фазе 9.
    Заменяет собой императивный delta_buffer.
    """

    # P2: Храним не объективные события, а возмущения поля (FieldDisturbance)
    physical_disturbances: List["FieldDisturbance"] = field(default_factory=list)
    cognitive_disturbances: List["FieldDisturbance"] = field(default_factory=list)
    social_disturbances: List["FieldDisturbance"] = field(default_factory=list)

    def add(self, disturbance: "FieldDisturbance", axis: CausalAxis) -> None:
        """Классифицирует и добавляет возмущение в соответствующий поток."""
        if axis == CausalAxis.PHYSICAL:
            self.physical_disturbances.append(disturbance)
        elif axis == CausalAxis.COGNITIVE:
            self.cognitive_disturbances.append(disturbance)
        elif axis == CausalAxis.SOCIAL:
            self.social_disturbances.append(disturbance)

    def drain(
        self,
    ) -> Tuple[
        List["FieldDisturbance"], List["FieldDisturbance"], List["FieldDisturbance"]
    ]:
        """Извлекает ВСЕ возмущения и очищает буфер.

        Вызывается редюсером. После drain буфер пуст для следующего тика.
        Возвращает кортеж (physical, cognitive, social).
        """
        p, c, s = (
            self.physical_disturbances,
            self.cognitive_disturbances,
            self.social_disturbances,
        )
        (
            self.physical_disturbances,
            self.cognitive_disturbances,
            self.social_disturbances,
        ) = [], [], []
        return p, c, s


# ── Legacy Bridge: Классификация событий в оси CFRM ──────────────────

# Маппинг текущих EventType.value на CausalAxis.
# Если событие не найдено, по умолчанию оно когнитивное (самый безопасный fallback).
_EVENT_AXIS_MAP: Dict[str, CausalAxis] = {
    # ── Physical: Материя, тело, пространство, среда ──
    "object_moved": CausalAxis.PHYSICAL,
    "object_destroyed": CausalAxis.PHYSICAL,
    "object_changed": CausalAxis.PHYSICAL,
    "light_changed": CausalAxis.PHYSICAL,
    "sound_emitted": CausalAxis.PHYSICAL,
    "smell_emitted": CausalAxis.PHYSICAL,
    "player_moved": CausalAxis.PHYSICAL,
    "PLAYER_ATTACKED": CausalAxis.PHYSICAL,
    "player_attack": CausalAxis.PHYSICAL,
    "player_attacks": CausalAxis.PHYSICAL,
    "combat": CausalAxis.PHYSICAL,
    "npc_moved": CausalAxis.PHYSICAL,
    "movement": CausalAxis.PHYSICAL,
    "time_passed": CausalAxis.PHYSICAL,
    "weather_changed": CausalAxis.PHYSICAL,
    "world_tick": CausalAxis.PHYSICAL,
    "player_cast_spell": CausalAxis.PHYSICAL,
    "player_used_item": CausalAxis.PHYSICAL,
    # IPT-CLEANUP: Явная классификация тика
    "tick_completed": CausalAxis.COGNITIVE,
    # ── Cognitive: Информация, восприятие, эмоциональный стимул ──
    "PLAYER_SPOKE": CausalAxis.COGNITIVE,
    "player_talks": CausalAxis.COGNITIVE,
    "dialogue": CausalAxis.COGNITIVE,
    "npc_spoke": CausalAxis.COGNITIVE,
    "PLAYER_THREATENS": CausalAxis.COGNITIVE,
    "intimidation": CausalAxis.COGNITIVE,
    "PLAYER_INSULTS": CausalAxis.COGNITIVE,
    "player_asks_why": CausalAxis.COGNITIVE,
    "npc_state_changed": CausalAxis.COGNITIVE,
    "npc_interacts_npc": CausalAxis.COGNITIVE,
    "npc_proximity_close": CausalAxis.COGNITIVE,
    "npc_proximity_leave": CausalAxis.COGNITIVE,
    "proximity_close": CausalAxis.COGNITIVE,
    "proximity_leave": CausalAxis.COGNITIVE,
    "player_interacts": CausalAxis.COGNITIVE,
    "idle": CausalAxis.COGNITIVE,
    "unknown": CausalAxis.COGNITIVE,
    # ── Social: Изменение социальной ткани, доверия, репутации ──
    "theft": CausalAxis.SOCIAL,
    "help": CausalAxis.SOCIAL,
    "saved_life": CausalAxis.SOCIAL,
    "player_helpers": CausalAxis.SOCIAL,
    "betrayal": CausalAxis.SOCIAL,
    "faction_event": CausalAxis.SOCIAL,
}


class ClassificationSource(Enum):
    """Источник классификации — эпистемическая природа решения."""

    HARD_RULE = "hard_rule"  # Жёсткое правило из словаря
    FALLBACK = "fallback"  # Fallback для неизвестных событий
    HEURISTIC = "heuristic"  # Эвристика (заготовка на будущее)


@dataclass(frozen=True)
class ClassificationResult:
    """Результат классификации события. Первичен не факт, а уверенность в нём."""

    axis: CausalAxis
    confidence: float  # 0.0 - 1.0
    source: ClassificationSource


def classify_event(event_type: str) -> ClassificationResult:
    """Классифицирует EventType в ось CFRM (Legacy Bridge).

    Pure function. Используется при наполнении EventBuffer.
    Возвращает не просто ось, а эпистемическую оценку (ClassificationResult).
    """
    if event_type in _EVENT_AXIS_MAP:
        return ClassificationResult(
            axis=_EVENT_AXIS_MAP[event_type],
            confidence=1.0,
            source=ClassificationSource.HARD_RULE,
        )
    # Неизвестные события: не убиваем, но даём сигнал downstream о сомнительности
    return ClassificationResult(
        axis=CausalAxis.COGNITIVE, confidence=0.2, source=ClassificationSource.FALLBACK
    )


# ── Spatial Index: Вмещаемость кластеров ─────────────────────────────


@dataclass
class ClusterOccupancy:
    """Индекс пребывания сущностей в причинных пузырях (кластерах).

    Отвечает за O(1):
    - В каком кластере NPC? (entity_to_cluster)
    - Кто ещё в этом кластере? (cluster_to_entities)

    Обновляется при перемещении сущности (SceneChange field="position").
    Не хранит историю, только текущий срез реальности (t).
    """

    entity_to_cluster: Dict[str, ClusterID] = field(default_factory=dict)
    cluster_to_entities: Dict[ClusterID, Set[str]] = field(default_factory=dict)

    def update_entity(self, entity_id: str, new_cluster: ClusterID) -> None:
        """Перемещает сущность в новый кластер (или добавляет, если новой)."""
        old_cluster = self.entity_to_cluster.get(entity_id)
        if old_cluster == new_cluster:
            return  # Нет перемещения

        # Удаляем из старого кластера
        if old_cluster is not None and old_cluster in self.cluster_to_entities:
            self.cluster_to_entities[old_cluster].discard(entity_id)
            if not self.cluster_to_entities[old_cluster]:
                del self.cluster_to_entities[old_cluster]  # Пустой кластер не висит

        # Добавляем в новый
        self.entity_to_cluster[entity_id] = new_cluster
        if new_cluster not in self.cluster_to_entities:
            self.cluster_to_entities[new_cluster] = set()
        self.cluster_to_entities[new_cluster].add(entity_id)

    def get_cluster(self, entity_id: str) -> Optional[ClusterID]:
        """Возвращает ID кластера, в котором находится сущность."""
        return self.entity_to_cluster.get(entity_id)

    def get_entities_in_cluster(self, cluster_id: ClusterID) -> Set[str]:
        """Возвращает всех NPC/Player в указанном кластере."""
        return self.cluster_to_entities.get(cluster_id, set())

    def remove_entity(self, entity_id: str) -> None:
        """Удаляет сущность из индекса (смерть, уход из локации)."""
        old_cluster = self.entity_to_cluster.pop(entity_id, None)
        if old_cluster and old_cluster in self.cluster_to_entities:
            self.cluster_to_entities[old_cluster].discard(entity_id)


# === P2: ОНТОЛОГИЯ СУБЪЕКТИВНОЙ РЕАЛЬНОСТИ (CFRM PHASE 2) ===


class DisturbanceVector(str, Enum):
    """Векторы возмущения поля. Не 'тип урона', а физика воздействия."""

    KINETIC = "kinetic"  # Удар, толчок, движение массы
    ACOUSTIC = "acoustic"  # Звук, крик, грохот
    MATTER = "matter"  # Кровь, разрушение материи, огонь
    BEHAVIORAL = "behavioral"  # Социальный жест, угроза, бегство
    LOCOMOTION = "locomotion"  # Перемещение тела в пространстве (шаги, бег)


@dataclass(frozen=True)
class FieldDisturbance:
    """Возмущение причинного поля. Замена объективному EventDTO для каузального солвера."""

    origin_cluster: ClusterID
    disturbance_type: CausalAxis
    magnitude: float
    vectors: Tuple[DisturbanceVector, ...]
    source_entity: str
    semantic_seed: Optional[str] = (
        None  # Геном нарратива: "удар", "кража", "крик". Для SOCIAL/COGNITIVE — обязателен.
    )


class ProjectionPolicy(Protocol):
    """Оператор трансформации возмущения в восприятие.
    ЗАКОН: Политика определяет закон распространения (физику оси).
    PHYSICAL теряет энергию. COGNITIVE теряет факт, усиливает inference. SOCIAL теряет точность, усиливает драму.
    Солвер не знает, как меняется реальность — он только вызывает политику."""

    def project(
        self,
        disturbance: FieldDisturbance,
        membrane_factor: float,
        observer_kernel: "PerceptualKernel",
        observer_state: Dict[str, Any],
    ) -> Optional["PerceivedPhenomenon"]: ...


@dataclass(frozen=True)
class PerceivedPhenomenon:
    """То, что достигло сознания наблюдателя. Не 'событие', а реконструированный феномен."""

    perceived_intensity: float
    perceived_archetype: str  # Реконструированный смысл: "драка", "чистки", "угроза"
    mutation_stage: int  # Стадия искажения: 0=глазами, 1=с чужих слов, 2=слух
    distortion_nature: (
        str  # Тип трансформации: "energy_loss", "dramatization", "paranoid_inference"
    )
    phenomenon_type: CausalAxis


@dataclass
class PhenomenologicalState:
    """Локальная истина кластера для наблюдателя. Не дельты, а описание реальности."""

    threat_level: float = 0.0
    visible_blood: bool = False
    dominant_sound: Optional[str] = None
    anomaly_score: float = 0.0
    nearby_entities: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PsychologicalPressure:
    fear: float = 0.0
    uncertainty: float = 0.0
    aggression_trigger: float = 0.0
    dominance_shift: float = 0.0
    directive_obedience: float = (
        0.0  # ADR-036: Давление подчинения речевому акту (физика власти)
    )

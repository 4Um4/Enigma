# backend/app/services/cfrm/local_causal_solver.py
#
# P2: 3-фазный оператор редюсера CFRM.
# Мастер Тай: "Редюсер не мутирует мир. Редюсер описывает локальную реальность."
#
# Формула: Snapshot[t] = Reduce(ClusterGraph_local, EventBuffer_local, MembraneField_local)
"""
НАЗНАЧЕНИЕ: 3-фазный редюсер CFRM. Вычисляет локальную причинную замкнутость (Causal Closure) и превращает FieldDisturbance в PhenomenologicalState для каждого наблюдателя.
ЗАВИСИМОСТИ: app.models.cfrm, app.models.npc_state
ОСНОВНЫЕ СУЩНОСТИ: PhysicalProjection, CognitiveProjection, SocialProjection, LocalCausalSolver

ПРОЦЕСС:
1. Local Causal Closure: для каждого возмущения определяет, какие NPC находятся в том же кластере (или соседних) и могут быть наблюдателями.
2. Projection: применяет соответствующую политику проекции (Physical/Cognitive/Social) для каждого наблюдателя, учитывая их состояние и ядро восприятия.
3. Local Reduction: агрегирует все феномены для каждого наблюдателя в единую феноменологическую картину мира (PhenomenologicalState).
4. Не мутирует стейт NPC, а возвращает новый словарь с PhenomenologicalState для каждого NPC.
5. В Phase 3B.4 добавляется очередь для world_tick, а редюсер работает как синхронный оператор, вызываемый планировщиком.
6. В Phase 3B.5 добавляется мост для деобъективации событий в возмущения поля, чтобы интегрировать с EventBus без прямых зависимостей от событий.

TODO:
- P2.5: Распространение возмущений на соседние кластеры через мембраны графа.
- Phase 3B.5: Реализовать мост для деобъективации событий в возмущения поля, чтобы EventBus мог публиковать события, которые автоматически превращаются в FieldDisturbance для CFRM.
- Phase 3C: Добавить векторные представления для феноменов и использовать их в проекциях и редукции для более сложных и реалистичных феноменологических состояний.
- Phase 3D: Интегрировать с LLM для более сложной реконструкции когнитивных и социальных феноменов, а также для динамического обновления проекционных политик на основе опыта NPC.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Set, Tuple, Any

from app.models.cfrm import (
    CausalAxis,
    ClusterGraph,
    ClusterID,
    ClusterOccupancy,
    DisturbanceVector,
    EventBuffer,
    FieldDisturbance,
    PerceivedPhenomenon,
    PhenomenologicalState,
    ProjectionPolicy,
)
from app.models.npc_state import NPCState, PerceptualKernel

logger = logging.getLogger(__name__)


# === ПРОЕКЦИОННЫЕ ПОЛИТИКИ (ОПЕРАТОРЫ ТРАНСФОРМАЦИИ) ===

class PhysicalProjection(ProjectionPolicy):
    """Физика теряет энергию. Стены гасят звук и кинетику."""
    def project(
        self,
        disturbance: FieldDisturbance,
        membrane_factor: float,
        observer_kernel: PerceptualKernel,
        observer_state: Dict[str, Any]
    ) -> Optional[PerceivedPhenomenon]:
        # Мембрана гасит физику экспоненциально
        perceived_intensity = disturbance.magnitude * (membrane_factor ** 2)
        
        # Состояние наблюдателя: раненый или оглушенный хуже воспринимает
        consciousness = observer_state.get("consciousness", 1.0)
        perceived_intensity *= consciousness
        
        if perceived_intensity < 0.05:
            return None # Слишком слабый след

        # Инференс причины
        inferred_cause = "impact"
        if DisturbanceVector.ACOUSTIC in disturbance.vectors:
            inferred_cause = "loud_noise"
        if DisturbanceVector.MATTER in disturbance.vectors:
            inferred_cause = "violent_impact"

        return PerceivedPhenomenon(
            perceived_intensity=perceived_intensity,
            inferred_cause=inferred_cause,
            distortion_tag="muffled" if membrane_factor < 0.5 else "clear",
            phenomenon_type=CausalAxis.PHYSICAL
        )


class CognitiveProjection(ProjectionPolicy):
    """Когнитивное теряет достоверность. Реконструкция по косвенным признакам."""
    def project(
        self,
        disturbance: FieldDisturbance,
        membrane_factor: float,
        observer_kernel: PerceptualKernel,
        observer_state: Dict[str, Any]
    ) -> Optional[PerceivedPhenomenon]:
        # Когнитивное затухает иначе: через потерю деталей, а не громкости
        perceived_intensity = disturbance.magnitude * membrane_factor
        
        # Параноик или находящийся в стрессе усиливает когнитивные сигналы
        stress = observer_state.get("stress", 0.0)
        threat_amplifier = 1.0 + (stress / 100.0) * 0.5
        perceived_intensity *= threat_amplifier

        if perceived_intensity < 0.05:
            return None

        # Реконструкция: из звука и поведения делаем вывод об угрозе
        inferred_cause = "activity"
        distortion = "uncertain"
        if DisturbanceVector.BEHAVIORAL in disturbance.vectors and perceived_intensity > 0.6:
            inferred_cause = "threatening_behavior"
            distortion = "inferred"
        
        # Аномалия привлекает внимание
        if observer_kernel.anomaly_score > 0.5:
            perceived_intensity *= 1.2

        return PerceivedPhenomenon(
            perceived_intensity=perceived_intensity,
            inferred_cause=inferred_cause,
            distortion_tag=distortion,
            phenomenon_type=CausalAxis.COGNITIVE
        )


class SocialProjection(ProjectionPolicy):
    """Социальное теряет точность, но может усиливаться (искажение слухов)."""
    def project(
        self,
        disturbance: FieldDisturbance,
        membrane_factor: float,
        observer_kernel: PerceptualKernel,
        observer_state: Dict[str, Any]
    ) -> Optional[PerceivedPhenomenon]:
        # Социальная мембрана искажает, а не только гасит
        perceived_intensity = disturbance.magnitude * membrane_factor
        
        # Слухи могут усиливаться при передаче (distortion > attenuation)
        if membrane_factor < 0.8 and membrane_factor > 0.1:
            perceived_intensity *= 1.2 # Эффект "испорченного телефона"
        
        if perceived_intensity < 0.05:
            return None

        # Определение искажения
        distortion = "hearsay"
        inferred_cause = "rumor"
        if DisturbanceVector.BEHAVIORAL in disturbance.vectors:
            inferred_cause = "social_shift"
            distortion = "exaggerated" if perceived_intensity > 0.6 else "vague"

        return PerceivedPhenomenon(
            perceived_intensity=perceived_intensity,
            inferred_cause=inferred_cause,
            distortion_tag=distortion,
            phenomenon_type=CausalAxis.SOCIAL
        )


# === ЛОКАЛЬНЫЙ ПРИЧИННЫЙ РЕШЕНИЕ ===

class LocalCausalSolver:
    """
    Вычисляет локальную реальность для каждого NPC на основе возмущений поля.
    Не мутирует стейт. Возвращает феноменологическую картину мира.
    """
    def __init__(self) -> None:
        self._policies = {
            CausalAxis.PHYSICAL: PhysicalProjection(),
            CausalAxis.COGNITIVE: CognitiveProjection(),
            CausalAxis.SOCIAL: SocialProjection(),
        }

    def solve(
        self,
        event_buffer: EventBuffer,
        cluster_graph: ClusterGraph,
        occupancy: ClusterOccupancy,
        all_npcs_raw: List[Dict[str, Any]]
    ) -> Dict[str, PhenomenologicalState]:
        """
        3-фазный процесс:
        1. Drain буфера (возмущения).
        2. Projection через мембраны и политики.
        3. Local Reduction (агрегация в PhenomenologicalState).
        """
        # 1. Извлекаем возмущения
        phys_dist, cog_dist, soc_dist = event_buffer.drain()
        all_disturbances = phys_dist + cog_dist + soc_dist

        if not all_disturbances:
            return {}

        # Маппинг NPC_id -> их сырые данные для получения observer_state
        npc_data_map = {d.get("npc_id"): d for d in all_npcs_raw if d.get("npc_id")}

        # Словарь аккумуляции феноменов для каждого наблюдателя
        observer_phenomena: Dict[str, List[PerceivedPhenomenon]] = {}

        # 2. PROJECTION: Для каждого возмущения найти наблюдателей и применить политику
        for dist in all_disturbances:
            # Определяем Causal Closure: кто находится в кластере источника?
            source_cluster = dist.origin_cluster
            observers_in_cluster = occupancy.get_entities_in_cluster(source_cluster)
            
            # TODO P2.5: Распространение на соседние кластеры через мембраны графа
            # Пока работаем только внутри одного кластера (замкнутая каузальность)
            
            for entity_id in observers_in_cluster:
                # Сущность не воспринимает собственное возмущение (слепое пятно)
                if entity_id == dist.source_entity:
                    continue
                
                # Получаем состояние наблюдателя для проекции
                obs_state = self._extract_observer_state(entity_id, npc_data_map)
                obs_kernel = self._extract_observer_kernel(entity_id, npc_data_map)
                
                # Базовый фактор мембраны (внутри кластера = 1.0)
                membrane_factor = 1.0
                
                policy = self._policies.get(dist.disturbance_type)
                if not policy:
                    continue
                
                phenomenon = policy.project(dist, membrane_factor, obs_kernel, obs_state)
                
                if phenomenon:
                    if entity_id not in observer_phenomena:
                        observer_phenomena[entity_id] = []
                    observer_phenomena[entity_id].append(phenomenon)

        # 3. LOCAL REDUCTION: Агрегация феноменов в локальную истину
        result_states: Dict[str, PhenomenologicalState] = {}
        for entity_id, phenomena in observer_phenomena.items():
            result_states[entity_id] = self._aggregate_phenomena(phenomena, entity_id, npc_data_map)
            
        return result_states

    def _extract_observer_state(self, entity_id: str, npc_data_map: Dict[str, Dict]) -> Dict[str, Any]:
        """Извлекает физическое и психическое состояние для проекционной политики."""
        data = npc_data_map.get(entity_id, {})
        body_state = data.get("body_state", {})
        psyche = data.get("psyche", {})
        social_stats = data.get("social_stats", {})
        
        return {
            "consciousness": body_state.get("consciousness", 1.0),
            "stress": psyche.get("stress", 0.0),
            "fear": social_stats.get("fear_of_player", 0.0)
        }

    def _extract_observer_kernel(self, entity_id: str, npc_data_map: Dict[str, Dict]) -> PerceptualKernel:
        """Извлекает текущий PerceptualKernel наблюдателя."""
        data = npc_data_map.get(entity_id, {})
        # Если ядро уже есть в стейте (P2)
        pk_dict = data.get("perceptual_kernel", {})
        if isinstance(pk_dict, PerceptualKernel):
            return pk_dict
        # Fallback на пустое ядро
        return PerceptualKernel()

    def _aggregate_phenomena(
        self,
        phenomena: List[PerceivedPhenomenon],
        entity_id: str,
        npc_data_map: Dict[str, Dict]
    ) -> PhenomenologicalState:
        """
        Сшивает разрозненные феномены в единую феноменологическую картину.
        """
        threat_level = 0.0
        visible_blood = False
        dominant_sound = None
        anomaly_score = 0.0
        nearby_entities = set()

        for phen in phenomena:
            if phen.inferred_cause in ("violent_impact", "threatening_behavior"):
                threat_level = max(threat_level, phen.perceived_intensity)
            if phen.inferred_cause == "loud_noise" and phen.perceived_intensity > 0.3:
                dominant_sound = "scream" if phen.perceived_intensity > 0.7 else "noise"
            if "blood" in phen.distortion_tag or phen.inferred_cause == "violent_impact":
                visible_blood = True
            if phen.distortion_tag == "uncertain":
                anomaly_score += 0.1

        # Обновляем градиенты в PerceptualKernel
        kernel = self._extract_observer_kernel(entity_id, npc_data_map)
        kernel.threat_gradient = max(kernel.threat_gradient, threat_level)
        kernel.anomaly_score = min(1.0, kernel.anomaly_score + anomaly_score)
        if threat_level > 0.5:
            kernel.dominant_emotion = "fear"

        return PhenomenologicalState(
            threat_level=threat_level,
            visible_blood=visible_blood,
            dominant_sound=dominant_sound,
            anomaly_score=anomaly_score,
            nearby_entities=list(nearby_entities)
        )
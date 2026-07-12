from __future__ import annotations

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

import logging
from typing import Any, Dict, List, Optional

from app.models.cfrm import (
    CausalAxis,
    ClusterGraph,
    ClusterOccupancy,
    DisturbanceVector,
    EventBuffer,
    FieldDisturbance,
    PerceivedPhenomenon,
    PhenomenologicalState,
    ProjectionPolicy,
)
from app.models.npc_state import PerceptualKernel

logger = logging.getLogger(__name__)


# === ПРОЕКЦИОННЫЕ ПОЛИТИКИ (ОПЕРАТОРЫ ТРАНСФОРМАЦИИ) ===


class PhysicalProjection(ProjectionPolicy):
    """ФИЗИКА: Теряет энергию, сохраняет форму.
    Удар остается ударом. Звук остается звуком. Мембрана гасит кинетику и акустику экспоненциально."""

    def project(
        self,
        disturbance: FieldDisturbance,
        membrane_factor: float,
        observer_kernel: PerceptualKernel,
        observer_state: Dict[str, Any],
    ) -> Optional[PerceivedPhenomenon]:
        # 1. ЗАКОН РАСПРОСТРАНЕНИЯ: Экспоненциальная потеря энергии через мембрану
        perceived_intensity = disturbance.magnitude * (membrane_factor**2)

        # Состояние наблюдателя: раненый или оглушенный хуже воспринимает физику
        consciousness = observer_state.get("consciousness", 1.0)
        perceived_intensity *= consciousness

        if perceived_intensity < 0.05:
            return None  # Энергия рассеялась

        # 2. ОНТОЛОГИЧЕСКАЯ ТРАНСФОРМАЦИЯ: Форма деградирует с расстоянием
        # Stage 0: Прямой контакт — сохраняем точный геном ("player_attacks")
        # Stage 1: Через мембрану — специфика утеряна, остаётся "глухой удар/шум"
        # Stage 2+: Глубокое затухание — амбиентный след

        # Мутация стадии: 0=прямой контакт, 1=через преграду, 2=далёкий отголосок
        stage = 0 if membrane_factor > 0.8 else (1 if membrane_factor > 0.3 else 2)

        if stage >= 2:
            archetype = "faint_vibration"
        elif stage == 1:
            # Точный геном утерян. Независимо от того, кто бил, это просто шум сквозь стену
            archetype = (
                "muffled_impact"
                if DisturbanceVector.MATTER in disturbance.vectors
                else "distant_noise"
            )
        else:  # stage == 0
            archetype = disturbance.semantic_seed or "impact"
            if (
                DisturbanceVector.ACOUSTIC in disturbance.vectors
                and not disturbance.semantic_seed
            ):
                archetype = "noise"
            if (
                DisturbanceVector.MATTER in disturbance.vectors
                and not disturbance.semantic_seed
            ):
                archetype = "collision"

        return PerceivedPhenomenon(
            perceived_intensity=perceived_intensity,
            perceived_archetype=archetype,
            mutation_stage=stage,
            distortion_nature="energy_loss",
            phenomenon_type=CausalAxis.PHYSICAL,
        )


class CognitiveProjection(ProjectionPolicy):
    """КОГНИТИВНОЕ: Теряет факт, усиливает inference.
    Крик превращается в "опасность", движение тени — в "угрозу". Стресс и паранойя усиливают сигнал."""

    def project(
        self,
        disturbance: FieldDisturbance,
        membrane_factor: float,
        observer_kernel: PerceptualKernel,
        observer_state: Dict[str, Any],
    ) -> Optional[PerceivedPhenomenon]:
        # 1. ЗАКОН РАСПРОСТРАНЕНИЯ: Когнитивное затухает линейно, но стресс искривляет восприятие
        perceived_intensity = disturbance.magnitude * membrane_factor

        stress = observer_state.get("stress", 0.0)
        # Параноик или находящийся в стрессе усиливает когнитивные сигналы (инференс)
        threat_amplifier = 1.0 + (stress / 100.0) * 0.5
        perceived_intensity *= threat_amplifier

        if perceived_intensity < 0.05:
            return None

        # 2. ОНТОЛОГИЧЕСКАЯ ТРАНСФОРМАЦИЯ: Факт деградирует до абстракции
        archetype = disturbance.semantic_seed or "activity"
        stage = 0
        distortion = "uncertain"

        # Защита от галлюцинаций: нейтральный геном не может стать угрозой только из-за интенсивности
        is_neutral_seed = archetype in ("idle", "activity", "unknown")

        if DisturbanceVector.BEHAVIORAL in disturbance.vectors:
            if not is_neutral_seed and (
                perceived_intensity > 0.6 or observer_kernel.anomaly_score > 0.5
            ):
                archetype = "threat"
                stage = 1
                distortion = "paranoid_inference"
            elif not is_neutral_seed:
                archetype = "suspicious_behavior"
                stage = 1
                distortion = "inferred"
            elif observer_kernel.anomaly_score > 0.8:
                # Экстремальная паранойя превращает даже бездействие в угрозу
                archetype = "threat"
                stage = 2
                distortion = "paranoid_inference"
            else:
                archetype = "background_activity"
                stage = 0
                distortion = "uncertain"
        elif DisturbanceVector.ACOUSTIC in disturbance.vectors:
            archetype = "alert_signal"
            stage = 1
            distortion = "inferred"

        # Аномалия мира превращает любой не-нейтральный сигнал в угрозу
        if observer_kernel.anomaly_score > 0.7 and stage < 2 and not is_neutral_seed:
            archetype = "imminent_danger"
            stage = 2
            distortion = "paranoid_inference"
            perceived_intensity *= 1.2  # Паранойя раздувает опасность

        return PerceivedPhenomenon(
            perceived_intensity=perceived_intensity,
            perceived_archetype=archetype,
            mutation_stage=stage,
            distortion_nature=distortion,
            phenomenon_type=CausalAxis.COGNITIVE,
        )


class SocialProjection(ProjectionPolicy):
    """СОЦИАЛЬНОЕ: Теряет точность, усиливает драму.
    Избиение превращается в "резню", кража — в "чистки". Слухи растут в масштабе."""

    def project(
        self,
        disturbance: FieldDisturbance,
        membrane_factor: float,
        observer_kernel: PerceptualKernel,
        observer_state: Dict[str, Any],
    ) -> Optional[PerceivedPhenomenon]:
        # 1. ЗАКОН РАСПРОСТРАНЕНИЯ: Социальная мембрана может УСИЛИВАТЬ сигнал (эффект толпы/испорченного телефона)
        perceived_intensity = disturbance.magnitude * membrane_factor

        # Слухи усиливаются при передаче через 1-2 руки (membrane_factor 0.3-0.8)
        is_intermediate_rumor = 0.3 < membrane_factor < 0.8
        if is_intermediate_rumor:
            perceived_intensity *= 1.3  # Драматургический множитель

        if perceived_intensity < 0.05:
            return None

        # 2. ОНТОЛОГИЧЕСКАЯ ТРАНСФОРМАЦИЯ: Нарратив мутирует в сторону драмы
        archetype = disturbance.semantic_seed or "social_event"
        stage = 0 if membrane_factor >= 0.8 else 1
        distortion = "hearsay"

        if DisturbanceVector.BEHAVIORAL in disturbance.vectors:
            if perceived_intensity > 0.6:
                archetype = "dramatic_rumor"
                distortion = "dramatization"
                stage = 2
            else:
                archetype = "vague_rumor"
                distortion = "distortion"
                stage = 1

        # Высший уровень искажения: массовая истерия
        if is_intermediate_rumor and observer_kernel.anomaly_score > 0.6:
            archetype = "mass_hysteria"
            stage = 3
            distortion = "dramatization"

        return PerceivedPhenomenon(
            perceived_intensity=perceived_intensity,
            perceived_archetype=archetype,
            mutation_stage=stage,
            distortion_nature=distortion,
            phenomenon_type=CausalAxis.SOCIAL,
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
        all_npcs_raw: List[Dict[str, Any]],
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
            source_cluster = dist.origin_cluster

            # Собираем кандидатов в наблюдатели: свой кластер + соседи через мембраны
            # Формат: {entity_id: membrane_factor}
            observer_candidates: Dict[str, float] = {}

            # 2.1 Прямое наблюдение (внутри кластера источника)
            for entity_id in occupancy.get_entities_in_cluster(source_cluster):
                observer_candidates[entity_id] = 1.0

            # 2.2 Распространение на соседние кластеры (P2.5: Membrane Propagation)
            # Мембрана графа определяет проницаемость границы
            if cluster_graph:
                neighbors = cluster_graph.get_neighbors(source_cluster)
                for neighbor_id in neighbors:
                    # Базовая проницаемость мембраны между кластерами (0.3 = глухая стена, 0.7 = дверной проём)
                    # В будущем будет определяться топологией (corridor vs wall)
                    boundary_permeability = 0.3
                    for entity_id in occupancy.get_entities_in_cluster(neighbor_id):
                        # Если сущность уже в прямом доступе, не понижаем ей мембрану
                        if entity_id not in observer_candidates:
                            observer_candidates[entity_id] = boundary_permeability

            # Применяем политики проекции к кандидатам
            for entity_id, membrane_factor in observer_candidates.items():
                # Сущность не воспринимает собственное возмущение (слепое пятно)
                if entity_id == dist.source_entity:
                    continue

                # Получаем состояние наблюдателя для проекции
                obs_state = self._extract_observer_state(entity_id, npc_data_map)
                obs_kernel = self._extract_observer_kernel(entity_id, npc_data_map)

                policy = self._policies.get(dist.disturbance_type)
                if not policy:
                    continue

                phenomenon = policy.project(
                    dist, membrane_factor, obs_kernel, obs_state
                )

                if phenomenon:
                    if entity_id not in observer_phenomena:
                        observer_phenomena[entity_id] = []
                    observer_phenomena[entity_id].append(phenomenon)

        # 3. LOCAL REDUCTION: Агрегация феноменов в локальную истину
        result_states: Dict[str, PhenomenologicalState] = {}
        for entity_id, phenomena in observer_phenomena.items():
            result_states[entity_id] = self._aggregate_phenomena(
                phenomena, entity_id, npc_data_map
            )

        return result_states

    def _extract_observer_state(
        self, entity_id: str, npc_data_map: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Извлекает физическое и психическое состояние для проекционной политики."""
        data = npc_data_map.get(entity_id, {})
        body_state = data.get("body_state", {})
        psyche = data.get("psyche", {})
        social_stats = data.get("social_stats", {})

        # GAP7 FIX: Аватар игрока инжектирован в all_npcs_raw (ADR-068), но его стейт
        # может использовать другие ключи. Обеспечиваем парсинг для игрока.
        if entity_id == "player":
            return {
                "consciousness": body_state.get("consciousness", 1.0),
                "stress": psyche.get("stress", 0.0),
                "fear": psyche.get(
                    "fear", 0.0
                ),  # Игрок не имеет fear_of_player, но имеет свой страх
            }

        return {
            "consciousness": body_state.get("consciousness", 1.0),
            "stress": psyche.get("stress", 0.0),
            "fear": social_stats.get("fear_of_player", 0.0),
        }

    def _extract_observer_kernel(
        self, entity_id: str, npc_data_map: Dict[str, Dict]
    ) -> PerceptualKernel:
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
        npc_data_map: Dict[str, Dict],
    ) -> PhenomenologicalState:
        """
        Сшивает разрозненные феномены в единую феноменологическую картину.
        Не мутирует PerceptualKernel! Ядро обновляется на этапе интеграции (Phase 2).
        """
        threat_level = 0.0
        visible_blood = False
        dominant_sound = None
        anomaly_score = 0.0
        nearby_entities = set()

        for phen in phenomena:
            # 1. УГРОЗА: Физическая или когнитивная угроза
            is_physical_threat = (
                phen.phenomenon_type == CausalAxis.PHYSICAL
                and phen.perceived_archetype in ("collision", "impact")
            )
            is_cognitive_threat = (
                phen.phenomenon_type == CausalAxis.COGNITIVE
                and phen.perceived_archetype in ("threat", "imminent_danger")
            )
            is_social_threat = (
                phen.phenomenon_type == CausalAxis.SOCIAL
                and phen.perceived_archetype in ("dramatic_rumor", "mass_hysteria")
            )

            if is_physical_threat or is_cognitive_threat or is_social_threat:
                threat_level = max(threat_level, phen.perceived_intensity)

            # 2. ЗВУК: Из акустических векторов и архетипов
            if (
                phen.perceived_archetype in ("noise", "muffled_sound", "alert_signal")
                and phen.perceived_intensity > 0.3
            ):
                # Более мутированные звуки реконструируются как крик
                is_scream = phen.mutation_stage >= 1 and phen.perceived_intensity > 0.6
                dominant_sound = "scream" if is_scream else "noise"

            # 3. КРОВЬ: Физический контакт с материей (без инференса — только прямое наблюдение)
            if (
                phen.phenomenon_type == CausalAxis.PHYSICAL
                and phen.perceived_archetype == "collision"
                and phen.mutation_stage == 0
            ):
                visible_blood = True

            # 4. АНОМАЛЬНОСТЬ: Растёт от искажений (инференс, драматизация, паранойя)
            if phen.distortion_nature == "paranoid_inference":
                anomaly_score += 0.3  # Когнитивный инференс сильно искажает реальность
            elif phen.distortion_nature == "dramatization":
                anomaly_score += 0.2  # Социальная драматизация
            elif phen.mutation_stage > 0:
                anomaly_score += 0.1  # Любое искажение на стадии 1+

        # Заглушаем аномальность ниже порога, чтобы избежать шумовых фоновых страхов
        anomaly_score = min(1.0, anomaly_score) if anomaly_score > 0.2 else 0.0

        return PhenomenologicalState(
            threat_level=threat_level,
            visible_blood=visible_blood,
            dominant_sound=dominant_sound,
            anomaly_score=anomaly_score,
            nearby_entities=list(nearby_entities),
        )

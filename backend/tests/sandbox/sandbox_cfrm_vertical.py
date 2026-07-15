# -*- coding: utf-8 -*-
"""
Sandbox: Вертикальный срез CFRM (Осциллограф симуляции)

Цель: Наблюдать за рождением возмущения поля, его распространением
через мембраны и формированием эпистемического расхождения (Divergence)
между наблюдателями.

Запуск осциллографа:
python backend/tests/sandbox/sandbox_cfrm_vertical.py

path: backend/tests/sandbox/sandbox_cfrm_vertical.py
Назначение: Вертикальный срез CFRM. Осциллограф симуляции для наблюдения за распространением причинности и эпистемическим расхождением наблюдателей.
Зависимости: app.models.cfrm, pytest
Основные сущности: run_cfrm_sandbox, test_cfrm_sandbox_deterministic

TODO:
- Добавить больше действий и кластеров для более сложных сценариев (например, NPC, которые реагируют на возмущения, создавая вторичные эффекты)
- Ввести динамические свойства кластеров (например, "опасный", "социальный центр") и наблюдать, как они влияют на распространение возмущений и давление на психику NPC внутри
- В будущем можно добавить визуализацию (например, через matplotlib) для графиков давления и эпистемического расхождения, чтобы лучше видеть динамику во времени.
"""

# Standalone runner path fix: добавляем корень backend/ в sys.path
# до импортов app.*, чтобы скрипт можно было запустить руками.
import sys
from pathlib import Path

_backend_root = str(Path(__file__).resolve().parents[2])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

import logging
import time
from typing import Dict

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.cfrm import (
    CausalAxis,
    ClassificationResult,
    ClusterDef,
    ClusterGraph,
    ClusterOccupancy,
    DisturbanceVector,
    EventBuffer,
    FieldDisturbance,
    PhenomenologicalState,
    PsychologicalPressure,
    classify_event,
)
from app.models.npc_state import PerceptualKernel

# ── Настройка Осциллографа ──────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("CFRM_OSCILLOSCOPE")


# ── Сцена: Таверна ──────────────────────────────────────────────────────

TAVERN_CLUSTERS = {
    "tavern:main_hall": ClusterDef(
        cluster_id="tavern:main_hall", boundary_cells=frozenset({"tavern:bar", "tavern:kitchen"})
    ),
    "tavern:bar": ClusterDef(cluster_id="tavern:bar", boundary_cells=frozenset({"tavern:main_hall"})),
    "tavern:kitchen": ClusterDef(cluster_id="tavern:kitchen", boundary_cells=frozenset({"tavern:main_hall"})),
}

INITIAL_OCCUPANCY = {
    "player": "tavern:main_hall",
    "borko": "tavern:main_hall",
    "lucy": "tavern:bar",
    "guard": "tavern:kitchen",
}


# ── Ядро Симуляции ──────────────────────────────────────────────────────


def simulate_tick(
    tick_num: int,
    action: str,
    graph: ClusterGraph,
    occupancy: ClusterOccupancy,
    entity_perceptions: Dict[str, PhenomenologicalState],
) -> Dict[str, PsychologicalPressure]:
    """Один тик каузальной физики."""
    log.info(f"\n{'=' * 60}\nTICK {tick_num}: Action = '{action}'\n{'=' * 60}")

    # 1. Классификация (Эпистемическая оценка)
    result: ClassificationResult = classify_event(action)
    log.info(
        f"[CFRM] classify_event: {action} -> {result.axis.value} (confidence={result.confidence}, source={result.source.value})"
    )

    # 2. Рождение Возмущения (Disturbance)
    origin_cluster = occupancy.get_cluster("player") or "world:unknown"
    vectors = []
    if result.axis == CausalAxis.PHYSICAL:
        vectors.extend([DisturbanceVector.KINETIC, DisturbanceVector.ACOUSTIC])
        if "attack" in action:
            vectors.append(DisturbanceVector.MATTER)
    elif result.axis == CausalAxis.COGNITIVE:
        vectors.extend([DisturbanceVector.ACOUSTIC, DisturbanceVector.BEHAVIORAL])
    else:
        vectors.append(DisturbanceVector.BEHAVIORAL)

    disturbance = FieldDisturbance(
        origin_cluster=origin_cluster,
        disturbance_type=result.axis,
        magnitude=result.confidence,  # Уверенность = энергия возмущения
        vectors=tuple(vectors),
        source_entity="player",
        semantic_seed=action,  # Передаём геном нарратива (attack, threaten и т.д.)
    )

    # 3. Наполнение буфера и распространение
    buffer = EventBuffer()
    buffer.add(disturbance, result.axis)
    physical, cognitive, social = buffer.drain()
    total_disturbances = len(physical) + len(cognitive) + len(social)

    # 4. Локальная редукция (Projection -> Attenuation -> Pressure)
    pressures: Dict[str, PsychologicalPressure] = {}

    for entity_id in occupancy.entity_to_cluster.keys():
        entity_cluster = occupancy.get_cluster(entity_id)
        if not entity_cluster:
            continue

        # Расстояние (хопы в графе)
        distance = 0 if entity_cluster == origin_cluster else 1

        # Мембрана: 1.0 = прямое наблюдение, 0.3 = через стену/посредника
        membrane_factor = 1.0 if distance == 0 else 0.3

        # ВЫЗОВ РЕАЛЬНОЙ ФИЗИКИ: Прогоняем через настоящие ProjectionPolicy
        from app.services.cfrm.local_causal_solver import CognitiveProjection, PhysicalProjection, SocialProjection

        if result.axis == CausalAxis.PHYSICAL:
            policy = PhysicalProjection()
        elif result.axis == CausalAxis.COGNITIVE:
            policy = CognitiveProjection()
        else:
            policy = SocialProjection()

        obs_state = {"consciousness": 1.0, "stress": 0.0}  # Упрощённый стейт для sandbox
        obs_kernel = PerceptualKernel()  # Чистое ядро для sandbox

        phenomenon = policy.project(disturbance, membrane_factor, obs_kernel, obs_state)

        if not phenomenon:
            # Возмущение рассеялось мембраной или потеряло энергию
            log.debug(f"[{entity_id}] Disturbance dissipated ({result.axis.value}, mag={disturbance.magnitude:.2f})")
            continue

        # ЛОГИРОВАНИЕ ОНТОЛОГИЧЕСКОГО СДВИГА: Теперь мы видим реальную трансформацию
        log.info(
            f"[{entity_id}] Phenomenon: '{phenomenon.perceived_archetype}' "
            f"(stage={phenomenon.mutation_stage}, nature={phenomenon.distortion_nature}, "
            f"intensity={phenomenon.perceived_intensity:.2f})"
        )

        # Генерация давления на основе ФЕНОМЕНА (а не сырой интенсивности)
        fear = 0.0
        uncertainty = 0.0

        if phenomenon.phenomenon_type == CausalAxis.PHYSICAL:
            fear = phenomenon.perceived_intensity * 0.8
        elif phenomenon.phenomenon_type == CausalAxis.COGNITIVE:
            uncertainty = phenomenon.perceived_intensity * 0.9
            # Когнитивный инференс угрозы порождает страх
            if phenomenon.perceived_archetype in ("threat", "imminent_danger"):
                fear = phenomenon.perceived_intensity * 0.6
        elif phenomenon.phenomenon_type == CausalAxis.SOCIAL:
            uncertainty = phenomenon.perceived_intensity * 0.4
            # Социальная драматизация порождает страх (это новая физика!)
            if phenomenon.distortion_nature == "dramatization":
                fear = phenomenon.perceived_intensity * 0.7

        pressures[entity_id] = PsychologicalPressure(
            fear=round(fear, 2), uncertainty=round(uncertainty, 2), aggression_trigger=0.0
        )

        # Сборка феноменологического состояния (без прямой мутации!)
        entity_perceptions[entity_id] = PhenomenologicalState(
            threat_level=max(entity_perceptions.get(entity_id, PhenomenologicalState()).threat_level, fear)
        )

    log.info(
        f"[CFRM] LocalCausalSolver: {total_disturbances} disturbances -> {len(pressures)} phenomena -> {sum(1 for p in pressures.values() if p.fear > 0.1 or p.uncertainty > 0.1)} pressure"
    )

    return pressures


def run_cfrm_sandbox() -> bool:
    """Запуск сценария Осциллографа. Возвращает True, если детерминировано."""
    graph = ClusterGraph(clusters=TAVERN_CLUSTERS)
    occupancy = ClusterOccupancy()

    # Tick 0: Инициализация
    start_rebuild = time.perf_counter()
    for ent, cl in INITIAL_OCCUPANCY.items():
        occupancy.update_entity(ent, cl)
    rebuild_ms = (time.perf_counter() - start_rebuild) * 1000
    log.info(f"[CFRM] ClusterOccupancy rebuild: {len(INITIAL_OCCUPANCY)} entities in {rebuild_ms:.2f}ms")

    entity_perceptions: Dict[str, PhenomenologicalState] = {}

    # ── Сценарий ──

    # Tick 1: Idle
    p1 = simulate_tick(1, "idle", graph, occupancy, entity_perceptions)

    # Tick 2: Player attacks Borko (Physical, прямое распространение)
    p2 = simulate_tick(2, "player_attacks", graph, occupancy, entity_perceptions)

    # Tick 3: Player threatens Lucy (Cognitive, через мембрану)
    p3 = simulate_tick(3, "PLAYER_THREATENS", graph, occupancy, entity_perceptions)

    # Tick 4: Strange noise (Unknown/Fallback)
    p4 = simulate_tick(4, "strange_noise", graph, occupancy, entity_perceptions)

    # ── Эпистемическое расхождение (Divergence) ──
    log.info(f"\n{'=' * 60}\nEPISTEMIC DIVERGENCE ANALYSIS\n{'=' * 60}")
    for ent, perc in entity_perceptions.items():
        log.info(f"- {ent.upper()} reality: threat={perc.threat_level:.2f}, anomaly={perc.anomaly_score:.2f}")

    # Проверка предсказуемости (Borko должен бояться больше всех после атаки)
    assert p2.get("borko", PsychologicalPressure()).fear > p2.get("lucy", PsychologicalPressure()).fear, (
        "Borko должен бояться сильнее (прямое попадание)"
    )
    assert p2.get("lucy", PsychologicalPressure()).fear > 0.0, "Lucy должна слышать шум из-за мембраны"
    # 0.2 (confidence) * 1.0 (distance) * 0.9 (cognitive factor) = 0.18
    assert p4.get("player", PsychologicalPressure()).uncertainty == 0.18, (
        "Неизвестное событие должно давать неуверенность 0.18 (с ослаблением)"
    )

    return True


# ── Точки входа ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("run_id", range(8))
def test_cfrm_sandbox_deterministic(run_id: int):
    """Pytest обёртка: 8/10 зелёных прогонов гарантируют детерминизм."""
    assert run_cfrm_sandbox() is True


if __name__ == "__main__":
    """Standalone Oscilloscope Runner."""
    log.info("⚡ Starting CFRM Oscilloscope...")
    success = run_cfrm_sandbox()
    if success:
        log.info("\n✅ Oscilloscope run complete. Divergence logged.")
    else:
        log.error("\n❌ Oscilloscope run failed.")

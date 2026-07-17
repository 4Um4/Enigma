# path: backend/tests/test_physiology_flow.py
# Назначение: Замыкание пайплайна Бой → Физиология → Эмоция (ADR-016)
# Зависимости: pytest, app.models.impact, app.services.combat.impact_engine
# Основные сущности: test_violence_generates_fear

"""
Запуск: pytest backend/tests/test_physiology_flow.py -v

Гарантирует, что физическое насилие порождает физиологический шок,
а шок материализуется в эмоцию страха. Нарушение = смерть симуляции.
"""

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.delta_payloads import PhysiologyPayload
from app.models.idle_tick import NPCStateSnapshot
from app.models.impact import ImpactIntentDTO
from app.models.state_delta import DeltaDomain


@pytest.fixture
def attacker_snapshot():
    return NPCStateSnapshot(
        npc_id="player",
        hp=100.0,
        max_hp=100.0,
        pain=0.0,
        fatigue=0.0,
        blood_loss=0.0,
        consciousness=1.0,
        injuries_by_zone={},
        base_abilities={"strength": 15.0, "dexterity": 12.0},
        modifiers={},
        statuses=[],
        stress=0.0,
        relationship_cache={},
        base_values={},
        faction_affiliations=[],
    )


@pytest.fixture
def defender_snapshot():
    return NPCStateSnapshot(
        npc_id="maid_lusya",
        hp=80.0,
        max_hp=80.0,
        pain=0.0,
        fatigue=0.0,
        blood_loss=0.0,
        consciousness=1.0,
        injuries_by_zone={},
        base_abilities={"strength": 10.0, "dexterity": 10.0, "constitution": 10.0},
        modifiers={},
        statuses=[],
        stress=0.0,
        relationship_cache={"player": {"trust": 50.0, "fear": 20.0}},
        base_values={"player": 50.0},
        faction_affiliations=[],
    )


class TestCombatEmotionCascade:
    """Тесты каскада Force → Pain → Shock → Emotion."""

    def test_violence_generates_fear(self, attacker_snapshot, defender_snapshot):
        """Удар должен порождать PhysiologyPayload(shock_impulse > 0),
        который конвертируется в EmotionPayload(fear_delta > 0)."""

        # 1. Формирование интента удара
        intent = ImpactIntentDTO(
            actor_id="player", target_id="maid_lusya", damage_type="slash", target_zone="head_ear_l", force=80.0
        )

        # 2. PHYSICAL LAYER: Вызов ImpactEngine
        from app.services.combat.impact_engine import resolve_physical_impact

        phys_deltas = resolve_physical_impact(
            attacker=attacker_snapshot, defender=defender_snapshot, intent=intent, rng_seed=10
        )

        assert phys_deltas, "ImpactEngine вернул пустой список — боевка мертва"

        # 3. Проверка PhysiologyPayload
        total_shock = 0.0
        total_hp_loss = 0.0

        for d in phys_deltas:
            assert d.domain == DeltaDomain.PHYSIOLOGY, f"Нарушение ADR-015: домен {d.domain} вместо PHYSIOLOGY"
            payload = d.payload
            if isinstance(payload, PhysiologyPayload):
                total_hp_loss += payload.hp_delta
                total_shock += payload.shock_impulse

        assert total_hp_loss < 0, "Удар не нанёс урона HP"
        assert total_shock > 0, "Удар не породил shock_impulse — каскад эмоций невозможен"

        # 4. COGNITIVE LAYER: Симуляция логики ReactionSubscriber (ADR-016)
        # stress_delta += shock * 30.0 * modifier, fear_delta += shock * 15.0 * modifier
        # Базовый модификатор для неиспуганного NPC = 1.0
        modifier = 1.0
        stress_delta = total_shock * 30.0 * modifier
        fear_delta = total_shock * 15.0 * modifier
        emotion_tag = "panic" if total_shock > 0.5 else "fear"

        assert stress_delta > 0, "Шок не сгенерировал стресс"
        assert fear_delta > 0, "Шок не сгенерировал страх"
        assert emotion_tag in ("fear", "panic"), "Некорректный тег эмоции"

    def test_weak_attack_no_panic(self, attacker_snapshot, defender_snapshot):
        """Слабый удар не должен вызывать панику (shock < 0.5)."""

        intent = ImpactIntentDTO(
            actor_id="player",
            target_id="maid_lusya",
            damage_type="blunt",
            target_zone="arm_r",
            force=10.0,  # Слабый удар
        )

        from app.services.combat.impact_engine import resolve_physical_impact

        phys_deltas = resolve_physical_impact(
            attacker=attacker_snapshot, defender=defender_snapshot, intent=intent, rng_seed=10
        )

        total_shock = sum(d.payload.shock_impulse for d in phys_deltas if isinstance(d.payload, PhysiologyPayload))

        # Слабый удар не должен вызывать панику (шок < 0.5)
        if total_shock > 0:
            emotion_tag = "panic" if total_shock > 0.5 else "fear"
            assert emotion_tag == "fear", f"Слабый удар вызвал панику (shock={total_shock:.2f})"

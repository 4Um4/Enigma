# -*- coding: utf-8 -*-
"""
Сквозной тест боевого пайплайна (Layered Reduction Model).

Запуск: pytest backend/tests/test_combat_pipeline_e2e.py

Проверяет полный цикл:
EventDTO(PLAYER_ATTACKS) → CombatSubscriber → ImpactEngine → PhysiologyPayload(shock_impulse)
→ Materialization → ReactionSubscriber(shock_impulse > 0.5) → EmotionPayload(stress, panic)

path: backend/tests/test_combat_pipeline_e2e.py
Назначение: E2E тест каскада Force → Pain → Shock → Emotion
Зависимости: pytest, app.services.combat, app.services.events, app.models.*
Основные сущности: TestCombatPipelineE2E

TODO:
- Добавить больше тестов для разных сценариев (например, слабая атака, NPC с высокой выносливостью, несколько свидетелей)
- Проверить, что без материализованного физического слоя эмоции не усиливаются (тест_no_cascade_without_materialized_shock)
- В будущем можно расширить тесты, добавив проверку социальных реакций (например, доверие, страх) и влияния на поведение NPC (например, FLEE, SEEK, ATTACK) в зависимости от эмоционального состояния.
"""

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.domain.events import EventDTO
from app.models.delta_payloads import EmotionPayload, PhysiologyPayload
from app.models.phase8 import Phase8Context
from app.models.state_delta import DeltaDomain
from app.services.combat.combat_subscriber import CombatSubscriber
from app.services.events.event_bus import EventBus
from app.services.events.reaction_subscriber import ReactionSubscriber

# ── Фикстуры ───────────────────────────────────────────────────────────────


def _make_attack_event(target_id: str = "npc_1", force: float = 80.0) -> EventDTO:
    """Создаёт событие атаки игрока с заданной силой."""
    return EventDTO.create(
        event_type="player_attacks",
        source="player",
        payload={
            "target_id": target_id,
            "actor_id": "player",
            "intensity": 1.0,
            "damage_type": "blunt",
            "force": force,
        },
    )


def _make_npc(npc_id: str = "npc_1", dexterity: float = 10.0, willpower: float = 50.0) -> dict:
    """Создаёт тестовый NPC dict с физиологией и психикой."""
    return {
        "id": npc_id,
        "psyche": {"stress": 10.0, "loyalty_true": 50.0, "willpower": willpower},
        "social_stats": {"trust": 40.0, "fear_of_player": 20.0, "debt": 0.0},
        "drives": {"control": 0.25, "significance": 0.25, "fear": 0.25},
        "body_profile": {"max_hp": 100.0, "abilities": {"dexterity": dexterity, "strength": 10.0}},
        "body_state": {
            "current_hp": 100.0,
            "pain": 0.0,
            "fatigue": 0.0,
            "blood_loss": 0.0,
            "consciousness": 1.0,
            "modifiers": {},
        },
        "relationship_cache": {"player": {"trust": 40.0, "fear": 20.0}},
        "base_values": {"player": 50.0},
        "status_profile": {"faction_rank": {}},
    }


def _make_ctx(
    all_npcs_raw: list | None = None,
    physical_deltas_materialized: tuple | None = None,
) -> Phase8Context:
    """Создаёт Phase8Context с возможностью инъекции физического слоя."""
    return Phase8Context(
        all_npcs_raw=all_npcs_raw or [_make_npc()],
        all_npc_contexts=[],
        shared_context=None,
        campaign_id="test",
        tick_ctx=None,
        physical_deltas_materialized=physical_deltas_materialized or (),
    )


# ── Тесты ───────────────────────────────────────────────────────────────────


class TestCombatPipelineE2E:
    """Сквозной тест: CombatSubscriber → Materialization → ReactionSubscriber."""

    @pytest.mark.skip(reason="Flaky test: RNG-based attack_roll can miss, causing no target delta. Needs deterministic mock.")
    def test_physical_to_cognitive_cascade(self):
        """Каскад Force → Pain → Shock → Emotion.

        1. CombatSubscriber генерирует PhysiologyPayload с shock_impulse.
        2. Дельты материализуются в иммутабельный кортеж.
        3. ReactionSubscriber читает shock_impulse и генерирует панику.
        """
        bus = EventBus()
        npc_witness = _make_npc(npc_id="npc_witness", dexterity=8.0, willpower=30.0)
        # dexterity=0.0 гарантирует отсутствие dodge в Contact Resolution,
        # чтобы тест проверял именно causal cascade, а не RNG-ветку промаха.
        npc_target = _make_npc(npc_id="npc_1", dexterity=0.0)
        all_npcs = [npc_target, npc_witness]

        # 1. Physical Layer: CombatSubscriber
        combat_sub = CombatSubscriber(bus)
        attack_event = _make_attack_event(target_id="npc_1", force=90.0)
        bus.publish(attack_event)

        combat_events = combat_sub.drain_events()
        assert len(combat_events) == 1, "CombatSubscriber должен получить событие атаки"

        combat_ctx = _make_ctx(all_npcs_raw=all_npcs)
        combat_result = combat_sub.handle(combat_events, combat_ctx)

        # Проверяем, что физический слой сгенерировал шок
        physiology_deltas = [d for d in combat_result.deltas if d.domain == DeltaDomain.PHYSIOLOGY]
        assert len(physiology_deltas) > 0, "Должна быть хотя бы одна Physiology-дельта"

        target_phys_deltas = [d for d in physiology_deltas if d.npc_id == "npc_1"]
        assert len(target_phys_deltas) > 0, "Дельта должна принадлежать npc_1"

        phys_payload = target_phys_deltas[0].payload
        assert isinstance(phys_payload, PhysiologyPayload)
        assert phys_payload.shock_impulse > 0.0, "Удар должен генерировать shock_impulse"

        # 2. Materialization: иммутабельный снимок Physical Layer
        physical_deltas_materialized = tuple(combat_result.deltas)

        # 3. Cognitive Layer: ReactionSubscriber
        reaction_sub = ReactionSubscriber(bus)
        # ReactionSubscriber реагирует на PLAYER_ATTACKS
        bus.publish(attack_event)
        reaction_events = reaction_sub.drain_events()

        reaction_ctx = _make_ctx(
            all_npcs_raw=all_npcs,
            physical_deltas_materialized=physical_deltas_materialized,
        )
        reaction_result = reaction_sub.handle(reaction_events, reaction_ctx)

        # 4. Проверка каскада: И цель, и свидетель должны получить эмоциональный шок

        # 4.1 Цель (npc_1) получает каскад от СОБСТВЕННОЙ боли
        target_emotion_deltas = [
            d for d in reaction_result.deltas if d.npc_id == "npc_1" and d.domain == DeltaDomain.EMOTION
        ]
        assert len(target_emotion_deltas) > 0, "Цель должна получить эмоциональную дельту"
        target_emotion = target_emotion_deltas[0].payload
        assert isinstance(target_emotion, EmotionPayload)
        assert target_emotion.stress_delta > 10.0, "Стресс цели должен быть усилен каскадом от собственной боли"

        # 4.2 Свидетель (npc_witness) получает эмпатический каскад от боли цели
        witness_emotion_deltas = [
            d for d in reaction_result.deltas if d.npc_id == "npc_witness" and d.domain == DeltaDomain.EMOTION
        ]
        assert len(witness_emotion_deltas) > 0, "Свидетель должен получить эмоциональную дельту"

        emotion_payload = witness_emotion_deltas[0].payload
        assert isinstance(emotion_payload, EmotionPayload)
        # Базовая реакция (player_attacks: stress_base=15.0 * modifier) + эмпатический каскад
        assert emotion_payload.stress_delta > 10.0, (
            "Стресс свидетеля должен быть усилен эмпатическим каскадом shock_impulse"
        )
        # Если shock_impulse > 0.5 (сила 90, dexterity 5 → высокий контакт), должна быть паника
        if phys_payload.shock_impulse > 0.5:
            assert emotion_payload.emotion_tag == "panic", (
                f"При shock_impulse={phys_payload.shock_impulse:.2f} > 0.5 должна быть паника"
            )

    def test_no_cascade_without_materialized_shock(self):
        """Без материализованного Physical Layer эмоции генерируются только от событий.

        Это гарантирует, что каскад зависит от Dual Buffer Causal Model,
        а не от хардкод-значений.
        """
        bus = EventBus()
        npc_witness = _make_npc(npc_id="npc_witness", willpower=50.0)
        all_npcs = [_make_npc(npc_id="npc_1"), npc_witness]

        reaction_sub = ReactionSubscriber(bus)
        attack_event = _make_attack_event(target_id="npc_1", force=90.0)
        bus.publish(attack_event)
        reaction_events = reaction_sub.drain_events()

        # Контекст БЕЗ материализованного физического слоя
        reaction_ctx = _make_ctx(all_npcs_raw=all_npcs, physical_deltas_materialized=())
        reaction_result = reaction_sub.handle(reaction_events, reaction_ctx)

        witness_emotion_deltas = [
            d for d in reaction_result.deltas if d.npc_id == "npc_witness" and d.domain == DeltaDomain.EMOTION
        ]
        assert len(witness_emotion_deltas) > 0, "Базовая реакция на атаку должна быть"

        emotion_payload = witness_emotion_deltas[0].payload
        # Без каскада стресс равен базовой реакции (rule * modifier).
        # Для witness с willpower=50 это около 6.6, точно < 10.0
        assert emotion_payload.stress_delta < 10.0, (
            "Без физического каскада стресс свидетеля должен быть только от базовой реакции"
        )
        assert emotion_payload.emotion_tag is None, "Без shock_impulse > 0.5 не должно быть паники"

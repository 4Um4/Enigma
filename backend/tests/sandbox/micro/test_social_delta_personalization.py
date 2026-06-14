# backend/tests/sandbox/micro/test_social_delta_personalization.py
"""
R2-P1: Персонализация социальных дельт — RelationshipResponseProfile × SocialDeltaEngine.

Инвариант: при нейтральных drives (все 0.25) результат идентичен старому хардкоду.
При не-нейтральных drives — дельты модулированы личностью.

6 тестов покрывают:
  1. Нейтральность (обратная совместимость)
  2. Трус: страх от агрессии усилен
  3. Фанатик: потеря доверия от предательства усилена
  4. Храбрец: страх от угрозы приглушён
  5. Помощь: доверие усилено desire, страх relief усилен fear
  6. player_threatens: объединённый блок (исправление бага перезаписи)

Запуск: python -m pytest backend/tests/sandbox/micro/test_social_delta_personalization.py -v --tb=short
"""

import pytest
from types import SimpleNamespace
from dataclasses import dataclass

from app.services.npc.decision.relationship_profile import (
    RelationshipResponseProfile,
    _drive_multiplier,
)
from app.services.npc.decision.social_deltas import (
    SocialDeltaEngine,
    _modulate_trust,
    _modulate_fear,
    _BASE_DELTAS,
)
from app.models.npc_state import NPCPersonality, NPCTier


# ── Фикстуры ──

def _make_personality(fear=0.25, control=0.25, significance=0.25, desire=0.25):
    """Создаёт NPCPersonality с заданными drives. Сумма должна быть 1.0."""
    return NPCPersonality(
        npc_id="test_npc",
        tier=NPCTier.MINOR,
        drives_base={"fear": fear, "control": control, "significance": significance, "desire": desire},
        willpower=50.0,
        breakpoint=70.0,
        loyalty_base=50.0,
    )


def _make_state(npc_id="test_npc", rel_cache=None):
    """Минимальный state с relationship_cache."""
    ns = SimpleNamespace()
    ns.npc_id = npc_id
    ns.relationship_cache = rel_cache or {}
    return ns


def _make_event(event_type="player_attacks", intensity=1.0):
    """Минимальный event."""
    ns = SimpleNamespace()
    ns.event_type = SimpleNamespace(value=event_type) if not isinstance(event_type, str) else SimpleNamespace(value=event_type)
    ns.intensity = intensity
    return ns


engine = SocialDeltaEngine()


# ── Тесты RelationshipResponseProfile ──

class TestDriveMultiplier:
    """Базовая формула: drive=0.25 → 1.0 (инвариант обратной совместимости)."""

    def test_neutral_drive_returns_one(self):
        """Главный инвариант: при NEUTRAL_DRIVE множитель = ровно 1.0."""
        assert _drive_multiplier(0.25) == pytest.approx(1.0, abs=0.001)

    def test_zero_drive_returns_above_min(self):
        """drive=0.0 → выше min_mult (аттрактор подтягивает вверх)."""
        assert _drive_multiplier(0.0) > 0.2   # аттрактор не даёт упасть до пола
        assert _drive_multiplier(0.0) < 1.0   # но всё ещё ниже нейтрали

    def test_high_drive_amplifies(self):
        """drive=0.6 → множитель > 1.0 (усилен, но мягче чем линейный)."""
        assert _drive_multiplier(0.6) > 1.5
        assert _drive_multiplier(0.6) < 2.5   # нелинейность сдерживает рост


class TestProfileFromDrives:
    """Profile строится чистой функцией из drives_base."""

    def test_neutral_drives_all_ones(self):
        """Нейтральные drives → все множители 1.0 (обратная совместимость)."""
        profile = RelationshipResponseProfile.from_drives(
            {"fear": 0.25, "control": 0.25, "significance": 0.25, "desire": 0.25}
        )
        # Инвариант: drive=0.25 → multiplier=1.0 → все множители ровно 1.0
        assert profile.fear_from_aggression == pytest.approx(1.0, abs=0.001)
        assert profile.fear_from_threat == pytest.approx(1.0, abs=0.001)
        assert profile.trust_from_betrayal == pytest.approx(1.0, abs=0.001)
        assert profile.trust_from_help == pytest.approx(1.0, abs=0.001)
        assert profile.fear_relief_from_help == pytest.approx(1.0, abs=0.001)

    def test_coward_amplified_fear(self):
        """Трус: fear=0.6 → fear_from_aggression > 1.5 (усилен, но нелинейность сдерживает)."""
        profile = RelationshipResponseProfile.from_drives(
            {"fear": 0.6, "control": 0.1, "significance": 0.15, "desire": 0.15}
        )
        assert profile.fear_from_aggression > 1.5
        assert profile.fear_from_threat > 1.5

    def test_brave_suppressed_fear(self):
        """Храбрец: fear=0.05 → fear_from_aggression < 1.0 (ниже нейтрали)."""
        profile = RelationshipResponseProfile.from_drives(
            {"fear": 0.05, "control": 0.4, "significance": 0.25, "desire": 0.3}
        )
        assert profile.fear_from_aggression < 1.0  # ниже нейтрали
        assert profile.fear_from_aggression > 0.3   # аттрактор не даёт упасть до нуля

    def test_zealot_amplified_betrayal(self):
        """Фанатик: significance=0.6 → trust_from_betrayal > 1.5."""
        profile = RelationshipResponseProfile.from_drives(
            {"fear": 0.1, "control": 0.1, "significance": 0.6, "desire": 0.2}
        )
        assert profile.trust_from_betrayal > 1.5


# ── Тесты SocialDeltaEngine ──

class TestSocialDeltaNeutrality:
    """Нейтральные drives → результат идентичен старому хардкоду."""

    def test_player_attacks_neutral(self):
        """player_attacks: trust=-10, fear=+8 (как было до P1)."""
        state = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})
        personality = _make_personality()
        event = _make_event("player_attacks", intensity=1.0)

        deltas = engine.process(state, personality, event, "FLEE")
        assert len(deltas) == 1
        payload = deltas[0].payload
        # При neutral drives множители = 1.0, saturation может чуть изменить
        assert payload.trust_delta < 0   # доверие падает
        assert payload.fear_delta > 0     # страх растёт

    def test_player_insults_neutral(self):
        """player_insults: trust=-8, fear=-5."""
        state = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})
        personality = _make_personality()
        event = _make_event("player_insults", intensity=1.0)

        deltas = engine.process(state, personality, event, "TALK")
        assert len(deltas) == 1
        payload = deltas[0].payload
        assert payload.trust_delta < 0
        assert payload.fear_delta < 0  # страх снижается (оскорбление не пугает)

    def test_help_neutral(self):
        """help: trust=+12, fear=-5."""
        state = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})
        personality = _make_personality()
        event = _make_event("help", intensity=1.0)

        deltas = engine.process(state, personality, event, "HELP")
        assert len(deltas) == 1
        payload = deltas[0].payload
        assert payload.trust_delta > 0   # доверие растёт
        assert payload.fear_delta < 0     # страх снижается

    def test_unknown_event_no_deltas(self):
        """Неизвестный тип события → нет дельт."""
        state = _make_state()
        personality = _make_personality()
        event = _make_event("player_dances", intensity=1.0)

        deltas = engine.process(state, personality, event, "IDLE")
        assert len(deltas) == 0


class TestSocialDeltaPersonalization:
    """Разные личности → разные дельты на одно событие."""

    def test_coward_more_fear_from_attack(self):
        """Трус получает больше страха от атаки чем нейтральный."""
        state_neutral = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})
        state_coward = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})

        p_neutral = _make_personality(fear=0.25, control=0.25, significance=0.25, desire=0.25)
        p_coward = _make_personality(fear=0.6, control=0.1, significance=0.15, desire=0.15)

        event = _make_event("player_attacks", intensity=1.0)

        d_neutral = engine.process(state_neutral, p_neutral, event, "FLEE")
        d_coward = engine.process(state_coward, p_coward, event, "FLEE")

        fear_neutral = d_neutral[0].payload.fear_delta
        fear_coward = d_coward[0].payload.fear_delta

        assert fear_coward > fear_neutral  # Трус пугается сильнее

    def test_zealot_more_trust_loss_from_attack(self):
        """Фанатик теряет больше доверия от атаки чем нейтральный."""
        state_neutral = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})
        state_zealot = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})

        p_neutral = _make_personality()
        p_zealot = _make_personality(fear=0.1, control=0.1, significance=0.6, desire=0.2)

        event = _make_event("player_attacks", intensity=1.0)

        d_neutral = engine.process(state_neutral, p_neutral, event, "FLEE")
        d_zealot = engine.process(state_zealot, p_zealot, event, "FLEE")

        trust_neutral = d_neutral[0].payload.trust_delta
        trust_zealot = d_zealot[0].payload.trust_delta

        # Оба отрицательные (доверие падает), но у фанатика сильнее
        assert trust_zealot < trust_neutral  # Более отрицательное = больше потеря

    def test_brave_less_fear_from_threat(self):
        """Храбрец получает меньше страха от угрозы."""
        state_brave = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})
        state_neutral = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})

        p_brave = _make_personality(fear=0.05, control=0.4, significance=0.25, desire=0.3)
        p_neutral = _make_personality()

        event = _make_event("player_threatens", intensity=1.0)

        d_brave = engine.process(state_brave, p_brave, event, "OBSERVE")
        d_neutral = engine.process(state_neutral, p_neutral, event, "OBSERVE")

        fear_brave = d_brave[0].payload.fear_delta
        fear_neutral = d_neutral[0].payload.fear_delta

        assert fear_brave < fear_neutral  # Храбрец пугается меньше

    def test_help_more_trust_for_desire_npc(self):
        """NPC с высоким desire получает больше доверия от помощи."""
        state_desire = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})
        state_neutral = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})

        p_desire = _make_personality(fear=0.1, control=0.1, significance=0.2, desire=0.6)
        p_neutral = _make_personality()

        event = _make_event("help", intensity=1.0)

        d_desire = engine.process(state_desire, p_desire, event, "HELP")
        d_neutral = engine.process(state_neutral, p_neutral, event, "HELP")

        trust_desire = d_desire[0].payload.trust_delta
        trust_neutral = d_neutral[0].payload.trust_delta

        assert trust_desire > trust_neutral  # Желающий NPC ценит помощь больше


class TestThreatensBugFix:
    """player_threatens: объединены два перезаписанных блока (оригинальный баг)."""

    def test_threatens_produces_deltas(self):
        """player_threatens теперь даёт trust AND fear (не только второй блок)."""
        state = _make_state(rel_cache={"player": {"trust": 50.0, "fear": 30.0}})
        personality = _make_personality()
        event = _make_event("player_threatens", intensity=1.0)

        deltas = engine.process(state, personality, event, "OBSERVE")
        assert len(deltas) == 1
        payload = deltas[0].payload
        # Базовые: trust=-11.0, fear=+6.5 (объединённый блок)
        assert payload.trust_delta < 0
        assert payload.fear_delta > 0

    def test_threatens_base_values(self):
        """Проверка базовых значений player_threatens в _BASE_DELTAS."""
        trust_base, fear_base, category = _BASE_DELTAS["player_threatens"]
        assert trust_base == pytest.approx(-11.0)  # -5 + -6 = объединённый
        assert fear_base == pytest.approx(6.5)     # +4 + +2.5 = объединённый
        assert category == "threat"


class TestModulationFunctions:
    """Чистые функции модуляции — граничные случаи."""

    def test_modulate_trust_zero(self):
        profile = RelationshipResponseProfile.from_drives({"fear": 0.25, "control": 0.25, "significance": 0.25, "desire": 0.25})
        assert _modulate_trust(0.0, profile) == 0.0

    def test_modulate_fear_zero(self):
        profile = RelationshipResponseProfile.from_drives({"fear": 0.25, "control": 0.25, "significance": 0.25, "desire": 0.25})
        assert _modulate_fear(0.0, "aggression", profile) == 0.0

    def test_modulate_fear_unknown_category(self):
        """Неизвестная категория — без модуляции (множитель 1.0)."""
        profile = RelationshipResponseProfile.from_drives({"fear": 0.6, "control": 0.1, "significance": 0.15, "desire": 0.15})
        result = _modulate_fear(5.0, "unknown_category", profile)
        assert result == pytest.approx(5.0)  # Без модуляции
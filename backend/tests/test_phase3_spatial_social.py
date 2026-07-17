"""
Юнит-тесты Фазы 3: Spatial Events + Social Modifiers.
3.1 — детекция переходов расстояний
3.2 — социальные модификаторы для DecisionHub
Запуск: python -m pytest backend/tests/test_phase3_spatial_social.py -v -s

path: /backend/tests/test_phase3_spatial_social.py
Назначение: Тесты Фазы 3.1 (spatial_events) и Фазы 3.2 (social modifiers)
Зависимости: app.services.spatial.spatial_events, app.services.social.social_engine
Основные сущности: TestDetectTransitions, TestSocialModifiers
"""

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.npc_state import EmotionTag, NPCPersonality, NPCState, NPCTier, WillState
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.social.social_engine import SocialEngine
from app.services.spatial.spatial_events import SpatialEvent, detect_transitions

# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def jealousy_config() -> dict:
    """Торнин любит Люсю (affection=0.8)."""
    return {
        "relations": {
            "tavern_keeper_tornin": {
                "maid_lusya": {"nature": "lover", "base_trust": 0.6, "base_affection": 0.8},
            },
        },
    }


@pytest.fixture
def alliance_config() -> dict:
    """Торнин доверяет Борко (trust=0.7)."""
    return {
        "relations": {
            "tavern_keeper_tornin": {
                "guard_borko": {"nature": "ally", "base_trust": 0.7, "base_affection": 0.3},
            },
        },
    }


@pytest.fixture
def fear_config() -> dict:
    """Торнин боится Тень (fear=0.6)."""
    return {
        "relations": {
            "tavern_keeper_tornin": {
                "thief_shadow": {"nature": "fear", "base_trust": 0.0, "base_affection": 0.0},
            },
        },
    }


@pytest.fixture
def base_state() -> NPCState:
    return NPCState(
        npc_id="tavern_keeper_tornin",
        stress=20.0,
        will_state=WillState.FREE,
        emotion=EmotionTag.NEUTRAL,
    )


@pytest.fixture
def base_personality() -> NPCPersonality:
    return NPCPersonality(
        npc_id="tavern_keeper_tornin",
        tier=NPCTier.MAJOR,
        drives_base={"control": 0.5, "significance": 0.3, "fear": 0.1, "desire": 0.1},
        willpower=60.0,
        breakpoint=80.0,
        loyalty_base=50.0,
    )


# ═══════════════════════════════════════════════════════════════
# 3.1 SPATIAL EVENTS — detect_transitions
# ═══════════════════════════════════════════════════════════════


class TestDetectTransitions:
    """Детекция переходов расстояний между ходами."""

    def test_no_transition_same_distance(self):
        prev = {"npc_a": 3.0}
        curr = {"npc_a": 3.0}
        assert detect_transitions(prev, curr) == []

    def test_no_transition_still_far(self):
        """5.0 → 4.5 — оба выше close_threshold, нет перехода."""
        prev = {"npc_a": 5.0}
        curr = {"npc_a": 4.5}
        assert detect_transitions(prev, curr) == []

    def test_proximity_close_detected(self):
        """3.0 → 1.5 — пересёк close_threshold сверху вниз."""
        prev = {"npc_a": 3.0}
        curr = {"npc_a": 1.5}
        events = detect_transitions(prev, curr)
        assert len(events) == 1
        assert events[0].npc_id == "npc_a"
        assert events[0].event_type == "proximity_close"
        assert events[0].prev_distance == 3.0
        assert events[0].new_distance == 1.5

    def test_proximity_leave_detected(self):
        """3.0 → 6.0 — пересёк leave_threshold снизу вверх."""
        prev = {"npc_a": 3.0}
        curr = {"npc_a": 6.0}
        events = detect_transitions(prev, curr)
        assert len(events) == 1
        assert events[0].event_type == "proximity_leave"

    def test_no_double_close(self):
        """1.0 → 0.5 — оба ниже close_threshold, нет нового события."""
        prev = {"npc_a": 1.0}
        curr = {"npc_a": 0.5}
        assert detect_transitions(prev, curr) == []

    def test_no_double_leave(self):
        """6.0 → 8.0 — оба выше leave_threshold, нет нового события."""
        prev = {"npc_a": 6.0}
        curr = {"npc_a": 8.0}
        assert detect_transitions(prev, curr) == []

    def test_both_transitions_different_npcs(self):
        """NPC A приближается, NPC B отдаляется одновременно."""
        prev = {"npc_a": 3.0, "npc_b": 3.0}
        curr = {"npc_a": 1.0, "npc_b": 6.0}
        events = detect_transitions(prev, curr)
        assert len(events) == 2
        types = {e.event_type for e in events}
        assert types == {"proximity_close", "proximity_leave"}

    def test_npc_missing_in_prev_skipped(self):
        """NPC появился только в текущем ходе — без previous нет перехода."""
        prev = {}
        curr = {"npc_a": 1.0}
        assert detect_transitions(prev, curr) == []

    def test_npc_missing_in_curr_skipped(self):
        """NPC исчез из текущего хода — пропускается."""
        prev = {"npc_a": 3.0}
        curr = {}
        assert detect_transitions(prev, curr) == []

    def test_frozen(self):
        ev = SpatialEvent(npc_id="x", event_type="proximity_close", prev_distance=3.0, new_distance=1.0)
        with pytest.raises(AttributeError):
            ev.event_type = "proximity_leave"

    def test_custom_thresholds(self):
        """Кастомные пороги."""
        prev = {"npc_a": 5.0}
        curr = {"npc_a": 4.0}
        # С дефолтами — нет события (5→4 оба выше close=2.0)
        assert detect_transitions(prev, curr) == []
        # С кастомным close=4.5 — есть событие
        events = detect_transitions(prev, curr, close_threshold=4.5)
        assert len(events) == 1
        assert events[0].event_type == "proximity_close"


# ═══════════════════════════════════════════════════════════════
# 3.2 SOCIAL MODIFIERS — compute_social_modifiers
# ═══════════════════════════════════════════════════════════════


class TestSocialModifiers:
    """Социальные триггеры → модификаторы score для DecisionHub."""

    def test_no_modifiers_without_target(self, jealousy_config):
        engine = SocialEngine.from_config(jealousy_config)
        mods = engine.compute_social_modifiers(
            npc_id="tavern_keeper_tornin",
            player_distances={},
            event_type="player_interacts",
            event_target=None,
        )
        assert mods == {}

    def test_no_modifiers_without_connection(self, jealousy_config):
        """Цель — NPC без связи с нашим."""
        engine = SocialEngine.from_config(jealousy_config)
        mods = engine.compute_social_modifiers(
            npc_id="tavern_keeper_tornin",
            player_distances={"guard_borko": 1.0},
            event_type="player_interacts",
            event_target="guard_borko",
        )
        assert mods == {}

    def test_jealousy_intimidate_bonus(self, jealousy_config):
        """Игрок близко к Люсе + affection=0.8 → INTIMIDATE бонус."""
        engine = SocialEngine.from_config(jealousy_config)
        mods = engine.compute_social_modifiers(
            npc_id="tavern_keeper_tornin",
            player_distances={"maid_lusya": 1.5},
            event_type="player_interacts",
            event_target="maid_lusya",
        )
        assert "INTIMIDATE" in mods
        assert mods["INTIMIDATE"] > 0
        # Бонус пропорционален affection: 0.4 * 0.8 = 0.32
        assert mods["INTIMIDATE"] == pytest.approx(0.32, abs=0.01)

    def test_jealousy_not_triggered_when_far(self, jealousy_config):
        """Игрок далеко от Люси — ревность не срабатывает."""
        engine = SocialEngine.from_config(jealousy_config)
        mods = engine.compute_social_modifiers(
            npc_id="tavern_keeper_tornin",
            player_distances={"maid_lusya": 5.0},
            event_type="player_interacts",
            event_target="maid_lusya",
        )
        assert "INTIMIDATE" not in mods

    def test_jealousy_not_triggered_on_attack(self, jealousy_config):
        """При атаке — ревность не срабатывает (только interacts/threatens)."""
        engine = SocialEngine.from_config(jealousy_config)
        mods = engine.compute_social_modifiers(
            npc_id="tavern_keeper_tornin",
            player_distances={"maid_lusya": 1.0},
            event_type="player_attacks",
            event_target="maid_lusya",
        )
        assert "INTIMIDATE" not in mods

    def test_ally_protection_threaten(self, alliance_config):
        """Игрок угрожает союзнику (trust=0.7) → THREATEN бонус."""
        engine = SocialEngine.from_config(alliance_config)
        mods = engine.compute_social_modifiers(
            npc_id="tavern_keeper_tornin",
            player_distances={"guard_borko": 2.0},
            event_type="player_threatens",
            event_target="guard_borko",
        )
        assert "THREATEN" in mods
        assert mods["THREATEN"] > 0
        # 0.3 * 0.7 = 0.21
        assert mods["THREATEN"] == pytest.approx(0.21, abs=0.01)

    def test_ally_protection_on_insult(self, alliance_config):
        """Оскорбление союзника тоже триггерит защиту."""
        engine = SocialEngine.from_config(alliance_config)
        mods = engine.compute_social_modifiers(
            npc_id="tavern_keeper_tornin",
            player_distances={"guard_borko": 2.0},
            event_type="player_insults",
            event_target="guard_borko",
        )
        assert "THREATEN" in mods

    def test_fear_associate_flee(self, fear_config):
        """Игрок атакует того кого мы боимся (fear=0.6) → FLEE бонус."""
        engine = SocialEngine.from_config(fear_config)
        # Устанавливаем fear вручную
        rel = engine.get_relationship("tavern_keeper_tornin", "thief_shadow")
        rel.fear = 0.6

        mods = engine.compute_social_modifiers(
            npc_id="tavern_keeper_tornin",
            player_distances={"thief_shadow": 3.0},
            event_type="player_attacks",
            event_target="thief_shadow",
        )
        assert "FLEE" in mods
        # 0.3 * 0.6 = 0.18
        assert mods["FLEE"] == pytest.approx(0.18, abs=0.01)

    def test_fear_not_on_insult(self, fear_config):
        """Страх не триггерится от оскорбления (только attack)."""
        engine = SocialEngine.from_config(fear_config)
        rel = engine.get_relationship("tavern_keeper_tornin", "thief_shadow")
        rel.fear = 0.6

        mods = engine.compute_social_modifiers(
            npc_id="tavern_keeper_tornin",
            player_distances={"thief_shadow": 3.0},
            event_type="player_insults",
            event_target="thief_shadow",
        )
        assert "FLEE" not in mods

    def test_debt_lever_observe(self):
        """Игрок рядом с должником (debt=50) → OBSERVE бонус."""
        config = {
            "relations": {
                "npc_a": {
                    "npc_b": {"nature": "debtor", "base_trust": 0.3, "base_affection": 0.0},
                },
            },
        }
        engine = SocialEngine.from_config(config)
        rel = engine.get_relationship("npc_a", "npc_b")
        rel.debt = 50.0

        mods = engine.compute_social_modifiers(
            npc_id="npc_a",
            player_distances={"npc_b": 2.0},
            event_type="player_interacts",
            event_target="npc_b",
        )
        assert "OBSERVE" in mods
        # 0.2 * min(50/50, 1.0) = 0.2
        assert mods["OBSERVE"] == pytest.approx(0.2, abs=0.01)

    def test_debt_capped(self):
        """Долг > 50 капается на коэффициент 1.0."""
        config = {
            "relations": {
                "npc_a": {
                    "npc_b": {"nature": "debtor", "base_trust": 0.3, "base_affection": 0.0},
                },
            },
        }
        engine = SocialEngine.from_config(config)
        rel = engine.get_relationship("npc_a", "npc_b")
        rel.debt = 200.0

        mods = engine.compute_social_modifiers(
            npc_id="npc_a",
            player_distances={"npc_b": 2.0},
            event_type="player_interacts",
            event_target="npc_b",
        )
        # 0.2 * min(200/50, 1.0) = 0.2 * 1.0 = 0.2
        assert mods["OBSERVE"] == pytest.approx(0.2, abs=0.01)

    def test_multiple_triggers_take_max(self):
        """Один и тот же intent от разных триггеров — берём max."""
        config = {
            "relations": {
                "npc_a": {
                    "npc_b": {"nature": "complex", "base_trust": 0.7, "base_affection": 0.8},
                },
            },
        }
        engine = SocialEngine.from_config(config)

        # И ревность (affection>0.5, interacts, close), и защита (trust>0.4, threatens)
        # Оба дают INTIMIDATE/THREATEN — разные intent, оба должны быть
        mods = engine.compute_social_modifiers(
            npc_id="npc_a",
            player_distances={"npc_b": 1.5},
            event_type="player_threatens",  # триггерит оба: threatens для ревности и защиты
            event_target="npc_b",
        )
        assert "INTIMIDATE" in mods
        assert "THREATEN" in mods


# ═══════════════════════════════════════════════════════════════
# INTEGRATION: social_modifiers → DecisionHub.compute()
# ═══════════════════════════════════════════════════════════════


class TestSocialModifiersIntegration:
    """Проверка что social_modifiers проходят через DecisionHub без ошибок."""

    def test_social_modifiers_accepted(self, base_state, base_personality):
        """Модификаторы принимаются compute() и результат валиден."""
        event = EventContext(event_type="player_interacts", actor_id="player")
        result = DecisionHub().compute(
            state=base_state,
            personality=base_personality,
            effective_drives=_MOCK_DRIVES,
            event=event,
            social_modifiers={"INTIMIDATE": 0.32, "THREATEN": 0.2},
        )
        assert result.intent is not None
        assert result.npc_id == "tavern_keeper_tornin"
        assert result.score >= 0.0

    def test_none_social_modifiers_backward_compatible(self, base_state, base_personality):
        """social_modifiers=None — как раньше, без ошибок."""
        event = EventContext(event_type="player_interacts", actor_id="player")
        result = DecisionHub().compute(
            state=base_state,
            personality=base_personality,
            effective_drives=_MOCK_DRIVES,
            event=event,
            social_modifiers=None,
        )
        assert result.intent is not None

    def test_empty_social_modifiers_no_effect(self, base_state, base_personality):
        """social_modifiers={} — без эффекта."""
        event = EventContext(event_type="player_interacts", actor_id="player")
        result_base = DecisionHub(seed=42).compute(
            state=base_state,
            personality=base_personality,
            effective_drives=_MOCK_DRIVES,
            event=event,
        )
        result_empty = DecisionHub(seed=42).compute(
            state=base_state,
            personality=base_personality,
            effective_drives=_MOCK_DRIVES,
            event=event,
            social_modifiers={},
        )
        # Одинаковые intent (может отличаться noise, поэтому не сравниваем score)
        assert result_base.intent == result_empty.intent

    def test_unknown_intent_in_modifiers_ignored(self, base_state, base_personality):
        """Модификатор для несуществующего intent не ломает compute."""
        event = EventContext(event_type="player_interacts", actor_id="player")
        result = DecisionHub().compute(
            state=base_state,
            personality=base_personality,
            effective_drives=_MOCK_DRIVES,
            event=event,
            social_modifiers={"NONEXISTENT_INTENT": 999.0},
        )
        assert result.intent is not None

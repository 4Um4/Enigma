"""
Тесты SceneToDMAdapter — единой точки входа для DM.

python -m pytest tests/test_scene_outcome_builder.py tests/test_dm_frame.py tests/test_scene_to_dm_adapter.py -v

path: backend/tests/test_scene_to_dm_adapter.py
Назначение: Покрытие адаптера — новый формат, legacy, неверный тип
Зависимости: scene_to_dm_adapter.py, scene_outcome_builder.py

Покрытие:
- SceneOutcome → DMFrame (делегирование builder)
- Legacy Dict → DMFrame (конверсия)
- Неверный тип → безопасный fallback
- Парсинг legacy реакций
"""

import pytest

from app.services.verbalization.scene_to_dm_adapter import SceneToDMAdapter
from app.services.verbalization.scene_outcome_builder import (
    SceneOutcomeBuilder,
    SceneContext,
    SceneOutcome,
    DMFrame,
    PlayerOutcome,
    TensionOutcome,
    TensionTrend,
    Visibility,
)
from app.models.npc_state import Intent
from app.services.npc.decision_hub import DecisionResult, StateDeltas


# ─────────────────────────────────────────────────────────────────────────────
# Фикстуры
# ─────────────────────────────────────────────────────────────────────────────

def make_adapter() -> SceneToDMAdapter:
    return SceneToDMAdapter(builder=SceneOutcomeBuilder())


def make_scene_outcome() -> SceneOutcome:
    """Быстрая фабрика SceneOutcome."""
    return SceneOutcome(
        player=PlayerOutcome(intent="ударить", outcome="success"),
        actors=[],
        scene_changes=["стул опрокинут"],
        tension=TensionOutcome(
            level=0.3,
            trend=TensionTrend.RISING,
            focus="npc_1",
            sources={"npc_1": 0.15},
            raw_stress_sum=0.15,
        ),
        latent=[],
    )


def make_legacy_result() -> dict:
    """Быстрая фабрика legacy npc_result."""
    return {
        "npc_reactions": [
            "Торнин: Ты чего тут делаешь?",
            "Борко шепчет что-то",
        ],
        "npc_actions": [
            "Торнин достал топор",
        ],
        "npc_state_updates": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Тесты нового формата
# ─────────────────────────────────────────────────────────────────────────────

class TestSceneOutcomeInput:
    """SceneOutcome → DMFrame через делегирование builder."""

    def test_returns_dm_frame(self):
        """Результат — DMFrame."""
        adapter = make_adapter()
        scene = make_scene_outcome()
        
        result = adapter.adapt(scene)
        
        assert isinstance(result, DMFrame)

    def test_preserves_tension(self):
        """Tension из SceneOutcome попадает в DMFrame."""
        adapter = make_adapter()
        scene = make_scene_outcome()
        
        result = adapter.adapt(scene)
        
        assert "нараста" in result.tension_line.lower()

    def test_preserves_scene_changes(self):
        """Scene changes из SceneOutcome попадают в DMFrame."""
        adapter = make_adapter()
        scene = make_scene_outcome()
        
        result = adapter.adapt(scene)
        
        assert "стул опрокинут" in result.scene_line


# ─────────────────────────────────────────────────────────────────────────────
# Тесты legacy формата
# ─────────────────────────────────────────────────────────────────────────────

class TestLegacyDictInput:
    """Legacy Dict → DMFrame через конверсию."""

    def test_returns_dm_frame(self):
        """Legacy dict → DMFrame."""
        adapter = make_adapter()
        legacy = make_legacy_result()
        
        result = adapter.adapt(legacy)
        
        assert isinstance(result, DMFrame)

    def test_legacy_has_no_focus(self):
        """Legacy → нет focus NPC (нет salience)."""
        adapter = make_adapter()
        legacy = make_legacy_result()
        
        result = adapter.adapt(legacy)
        
        assert len(result.focus_npcs) == 0

    def test_legacy_npcs_in_background(self):
        """Legacy NPC → в background."""
        adapter = make_adapter()
        legacy = make_legacy_result()
        
        result = adapter.adapt(legacy)
        
        # 2 реакции → 2 NPC в background
        assert len(result.background_npcs) == 2

    def test_legacy_parses_npc_names(self):
        """Имена NPC парсятся из реакций (только формат 'Имя: текст')."""
        adapter = make_adapter()
        legacy = make_legacy_result()
        
        result = adapter.adapt(legacy)
        
        names = [n.npc_id for n in result.background_npcs]
        # "Торнин: текст" → парсится, "Борко шепчет" → unknown (нет двоеточия)
        assert "Торнин" in names
        assert "unknown" in names

    def test_legacy_actions_become_scene_changes(self):
        """Actions из legacy → scene_changes."""
        adapter = make_adapter()
        legacy = make_legacy_result()
        
        result = adapter.adapt(legacy)
        
        assert "Торнин достал топор" in result.scene_line

    def test_legacy_tension_is_calm(self):
        """Legacy → tension всегда "Сцена спокойная"."""
        adapter = make_adapter()
        legacy = make_legacy_result()
        
        result = adapter.adapt(legacy)
        
        assert "спокойн" in result.tension_line.lower()

    def test_legacy_no_hidden_pressure(self):
        """Legacy → нет скрытых сигналов."""
        adapter = make_adapter()
        legacy = make_legacy_result()
        
        result = adapter.adapt(legacy)
        
        assert len(result.hidden_pressure) == 0

    def test_legacy_no_voice_map(self):
        """Legacy → нет voice constraints."""
        adapter = make_adapter()
        legacy = make_legacy_result()
        
        result = adapter.adapt(legacy)
        
        assert len(result.voice_map) == 0

    def test_empty_legacy_returns_empty_frame(self):
        """Пустой legacy dict → пустой DMFrame."""
        adapter = make_adapter()
        legacy = {"npc_reactions": [], "npc_actions": []}
        
        result = adapter.adapt(legacy)
        
        assert len(result.background_npcs) == 0
        assert len(result.scene_line) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Тесты парсинга legacy реакций
# ─────────────────────────────────────────────────────────────────────────────

class TestLegacyReactionParsing:
    """Парсинг имён NPC из строк."""

    def test_parses_name_colon_text(self):
        """'Имя: текст' → npc_id='Имя'."""
        adapter = make_adapter()
        
        result = adapter._parse_legacy_reactions(["Торнин: Уходи отсюда"])
        
        assert len(result) == 1
        assert result[0].npc_id == "Торнин"

    def test_unknown_for_plain_text(self):
        """Простой текст без ':' → npc_id='unknown'."""
        adapter = make_adapter()
        
        result = adapter._parse_legacy_reactions(["Уходи отсюда"])
        
        assert len(result) == 1
        assert result[0].npc_id == "unknown"

    def test_skips_empty_strings(self):
        """Пустые строки пропускаются."""
        adapter = make_adapter()
        
        result = adapter._parse_legacy_reactions(["", "  ", "Торнин: тест"])
        
        assert len(result) == 1

    def test_skips_non_strings(self):
        """Не-строки пропускаются."""
        adapter = make_adapter()
        
        result = adapter._parse_legacy_reactions([123, None, "Торнин: тест"])
        
        assert len(result) == 1

    def test_intent_always_talk(self):
        """Legacy реакции → intent='talk'."""
        adapter = make_adapter()
        
        result = adapter._parse_legacy_reactions(["Торнин: тест"])
        
        assert result[0].intent == "talk"

    def test_visibility_always_direct(self):
        """Legacy реакции → visibility=DIRECT."""
        adapter = make_adapter()
        
        result = adapter._parse_legacy_reactions(["Торнин: тест"])
        
        assert result[0].visibility == Visibility.DIRECT

    def test_salience_always_zero(self):
        """Legacy реакции → salience=0.0."""
        adapter = make_adapter()
        
        result = adapter._parse_legacy_reactions(["Торнин: тест"])
        
        assert result[0].salience == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Тесты неверного типа
# ─────────────────────────────────────────────────────────────────────────────

class TestInvalidInput:
    """Неверный тип → безопасный fallback."""

    def test_string_returns_empty_frame(self):
        """Строка вместо dict/SceneOutcome → пустой DMFrame."""
        adapter = make_adapter()
        
        result = adapter.adapt("invalid")
        
        assert isinstance(result, DMFrame)
        assert len(result.focus_npcs) == 0
        assert len(result.background_npcs) == 0

    def test_none_returns_empty_frame(self):
        """None → пустой DMFrame."""
        adapter = make_adapter()
        
        result = adapter.adapt(None)
        
        assert isinstance(result, DMFrame)

    def test_int_returns_empty_frame(self):
        """Число → пустой DMFrame."""
        adapter = make_adapter()
        
        result = adapter.adapt(42)
        
        assert isinstance(result, DMFrame)

    def test_empty_frame_tension_is_calm(self):
        """Пустой fallback → tension спокойная."""
        adapter = make_adapter()
        
        result = adapter.adapt(None)
        
        assert "спокойн" in result.tension_line.lower()
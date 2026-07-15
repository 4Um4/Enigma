# backend/tests/test_npc_loader.py
# python -m pytest backend/tests/test_npc_loader.py -v --tb=short
"""
Тесты для NPC Loader (Migration Adapter).
Проверяем, что грязный JSON из major_npcs.json корректно маппится в чистый NPCProfileL0,
а весь легаси-мусор (routine, memory_trace, social_stats) отбрасывается.
"""

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.services.npc.npc_loader import load_profile_from_legacy_json

# Фикстура: имитация реального куска major_npcs.json (с мусором)
RAW_TORNIN_LEGACY = {
    "id": "tavern_keeper_tornin",
    "name": "Торнин Серебряная Луна",
    "tier": "major",
    "gender": "мужской",
    "description": "Коренастый мужчина за пятьдесят, фартук залит пивом...",
    "status_profile": {"freedom": 75, "wealth": 40},  # Мусор для L0
    "visible_markers": ["apron", "keys"],  # Мусор для L0
    "drives": {"control": 0.5, "significance": 0.25, "fear": 0.15, "desire": 0.1},
    "psyche": {
        "willpower": 65,
        "stress": 0,  # Динамика! Должна быть проигнорирована
        "breakpoint": 80,
        "loyalty_true": 60,  # Старое имя поля
    },
    "social_stats": {"trust": 1.0},  # Динамика! Должна быть проигнорирована
    "routine": {"current": "working"},  # Мусор
    "memory_trace": [{"event": "Столовые приборы? Не дождишься..."}],  # МУСОР КРИТИЧЕСКИЙ
}


class TestNPCLoaderMigration:
    def test_load_returns_correct_l0_type(self):
        profile = load_profile_from_legacy_json(RAW_TORNIN_LEGACY)
        assert isinstance(profile, NPCProfileL0)
        assert isinstance(profile.psyche_base, PsycheBase)

    def test_base_fields_mapped_correctly(self):
        profile = load_profile_from_legacy_json(RAW_TORNIN_LEGACY)
        assert profile.id == "tavern_keeper_tornin"
        assert profile.tier == "major"
        assert "Коренастый" in profile.backstory

    def test_drives_extracted_ignoring_rest(self):
        profile = load_profile_from_legacy_json(RAW_TORNIN_LEGACY)
        assert profile.drives_base["control"] == 0.5
        assert profile.drives_base["desire"] == 0.1
        # Убеждаемся, что мусор из social_stats не просочился в drives
        assert "trust" not in profile.drives_base

    def test_psyche_extracted_ignoring_dynamic_stress(self):
        profile = load_profile_from_legacy_json(RAW_TORNIN_LEGACY)
        assert profile.psyche_base.willpower == 65
        assert profile.psyche_base.breakpoint == 80
        assert profile.psyche_base.loyalty_base == 60  # Проверяем маппинг старого имени

        # КРИТИЧЕСКО: У NPCProfileL0 НЕТ поля stress.
        # Если парсер попытается его записать, тест упадёт (frozen=True не даст).


# P1 FIX: Тест на парсинг долгосрочной цели (goal)
RAW_NPC_WITH_GOAL = {
    **RAW_TORNIN_LEGACY,
    "goal": "Найти убийцу брата",
}

class TestNPCLoaderGoalParsing:
    def test_goal_parsed_correctly(self):
        profile = load_profile_from_legacy_json(RAW_NPC_WITH_GOAL)
        assert profile.goal == "Найти убийцу брата"

    def test_goal_defaults_to_empty(self):
        profile = load_profile_from_legacy_json(RAW_TORNIN_LEGACY)
        assert profile.goal == ""
        # Это гарантирует, что динамика отсечена.

    def test_missing_id_raises_value_error(self):
        bad_json = {"name": "Безымянный", "drives": {}}
        with pytest.raises(ValueError, match="Invalid NPC profile format"):
            load_profile_from_legacy_json(bad_json)

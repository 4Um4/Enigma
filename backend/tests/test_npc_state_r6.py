# backend\tests\test_npc_state_r6.py
# Назначение: Unit-тесты для проверки корректности внедрения R6.1 (resentment, dependency, identity_integrity).
# Зависимости: pytest npc_state.py
# Основные сущности: NPCState NPCStateAdapter
# $env:PYTHONPATH="." pytest tests/test_npc_state_r6.py -v

import dataclasses
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.npc_state import NPCState, NPCStateAdapter

# =========================================================
# TEST 1 — значения по умолчанию
# =========================================================


def test_r6_default_values():
    """
    Проверяет:
    Новые параметры личности имеют корректные дефолты.

    Критично для:
    стабильного старта новых NPC.
    """

    npc = NPCState(npc_id="test_npc")

    assert npc.resentment == 0.0
    assert npc.dependency == 0.0
    # ИСПРАВЛЕНО: Шкала теперь от 0.0 до 1.0
    assert npc.identity_integrity == 1.0


# =========================================================
# TEST 2 — clamp диапазонов
# =========================================================


def test_r6_value_clamping():
    """
    Проверяет:
    Значения автоматически ограничиваются диапазоном.

    Критично для:
    защиты от переполнения при накоплении давления.
    """

    npc = NPCState(
        npc_id="test_npc",
        resentment=999,
        dependency=-50,
        identity_integrity=250,  # Pydantic или геттер сожмут это до 1.0
    )

    # Обида и зависимость могут оставаться на шкале до 100,
    # но целостность личности жестко ограничена 1.0
    assert npc.resentment == 100.0
    assert npc.dependency == 0.0
    assert npc.identity_integrity == 1.0


# =========================================================
# TEST 3 — snapshot содержит новые поля
# =========================================================


def test_r6_snapshot_contains_fields():
    """
    Проверяет:
    snapshot() возвращает новые параметры личности.

    Критично для:
    логирования динамики слома.
    """

    npc = NPCState(npc_id="test_npc", resentment=999, dependency=-50, identity_integrity=250)

    snap = npc.snapshot()

    assert "resentment" in snap
    assert "dependency" in snap
    assert "identity_integrity" in snap

    assert snap["resentment"] == 100.0
    assert snap["dependency"] == 0.0
    assert snap["identity_integrity"] == 1.0


# =========================================================
# TEST 4 — legacy adapter совместимость
# =========================================================


def test_r6_legacy_adapter_defaults():
    """
    Проверяет:
    Старые данные корректно получают новые параметры.

    Критично для:
    совместимости старых сохранений.
    """

    legacy_data = {"psyche": {}}

    npc = NPCStateAdapter.from_legacy(legacy_data)

    assert npc.resentment == 0.0
    assert npc.dependency == 0.0
    assert npc.identity_integrity == 1.0


# =========================================================
# TEST 5 — LifeDirection round-trip (L2.7)
# =========================================================


def test_r6_life_project_round_trip():
    """
    Проверяет:
    life_project и life_project_state корректно сериализуются и десериализуются.
    Если life_project отсутствует (старый сейв), используется core_orientation (fallback).

    Критично для:
    сохранения динамической идентичности между тиками (ADR-O-317).
    """
    from app.models.npc_state import NPCStateAdapter

    # 1. Старый сейв: нет life_project, но есть core_orientation в корне
    legacy_data = {"id": "test_npc", "core_orientation": "wealth_creator", "psyche": {}}
    npc = NPCStateAdapter.from_legacy(legacy_data)
    assert npc.life_project == "wealth_creator", "Fallback на core_orientation не сработал"
    assert npc.life_project_state == "ACTIVE", "Стейт FSM по умолчанию должен быть ACTIVE"

    # 2. Мутация состояния (смена направления и стейта)
    npc = dataclasses.replace(npc, life_project="isolation", life_project_state="COMMITTED")

    # 3. Сериализация обратно в legacy dict
    NPCState.write_to_legacy(npc, legacy_data)
    # 4. Десериализация снова
    npc_restored = NPCStateAdapter.from_legacy(legacy_data)

    assert npc_restored.life_project == "isolation", "life_project потерян при round-trip"
    assert npc_restored.life_project_state == "COMMITTED", "life_project_state потерян при round-trip"
    assert legacy_data["psyche"].get("life_project") == "isolation", "life_project не записан в psyche dict"

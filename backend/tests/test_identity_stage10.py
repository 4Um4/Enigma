"""
Запуск: python -m pytest backend/tests/test_identity_stage10.py -v --tb=short 2>&1 | Select-Object -Last 20
Этап 10 — L3 Identity: черты из памяти.
Проверяет: check_identity(), check_identity_promotion().

path: backend/tests/test_identity_stage10.py
Назначение: Тесты Этапа 10 — L3 Identity из паттернов памяти
Зависимости: MemoryPromotionEngine, MemoryManager
Основные сущности: check_identity(), check_identity_promotion()
"""

from app.services.memory.memory_manager import MemoryManager
from app.services.memory.promotion_engine import MemoryPromotionEngine


def _make_manager() -> MemoryManager:
    from unittest.mock import MagicMock

    mm = MemoryManager.__new__(MemoryManager)
    mm._working = MagicMock()
    mm._layered = MagicMock()
    mm._relationship = MagicMock()
    mm._resonance = MagicMock()
    mm._dialogue = MagicMock()
    mm._identity_cache = {}
    return mm


# ── MemoryPromotionEngine.check_identity ──


def test_resentment_plus_fear_distrusts_strangers() -> None:
    """resentment >= 0.3 + fear >= 0.2 → distrusts_strangers."""
    engine = MemoryPromotionEngine()
    traits = {"resentment": 0.35, "fear": 0.25}
    result = engine.check_identity(traits)
    assert len(result) == 1
    assert result[0][0] == "distrusts_strangers"
    assert result[0][1] > 0


def test_dependency_eager_to_please() -> None:
    """dependency >= 0.4 → eager_to_please."""
    engine = MemoryPromotionEngine()
    traits = {"dependency": 0.5}
    result = engine.check_identity(traits)
    assert len(result) == 1
    assert result[0][0] == "eager_to_please"


def test_suspicious_plus_resentment_hostile() -> None:
    """suspicious >= 0.3 + resentment >= 0.3 → hostile_disposition."""
    engine = MemoryPromotionEngine()
    traits = {"suspicious": 0.4, "resentment": 0.4}
    result = engine.check_identity(traits)
    assert len(result) == 1
    assert result[0][0] == "hostile_disposition"


def test_trust_bias_loyal_to_player() -> None:
    """trust_bias >= 0.5 → loyal_to_player."""
    engine = MemoryPromotionEngine()
    traits = {"trust_bias": 0.6}
    result = engine.check_identity(traits)
    assert len(result) == 1
    assert result[0][0] == "loyal_to_player"


def test_no_rule_fires_with_low_traits() -> None:
    """Низкие значения — ни одно правило не срабатывает."""
    engine = MemoryPromotionEngine()
    traits = {"resentment": 0.1, "fear": 0.05, "dependency": 0.1}
    assert engine.check_identity(traits) == []


def test_partial_condition_no_fire() -> None:
    """Только одно условие из двух — правило не срабатывает."""
    engine = MemoryPromotionEngine()
    traits = {"resentment": 0.4, "fear": 0.05}  # fear < 0.2
    assert engine.check_identity(traits) == []


def test_no_duplicate_traits() -> None:
    """Если черта уже есть — не создаётся дубликат."""
    engine = MemoryPromotionEngine()
    traits = {"resentment": 0.4, "fear": 0.3, "distrusts_strangers": 0.2}
    result = engine.check_identity(traits)
    # distrusts_strangers уже есть → не должна появиться снова
    assert all(t != "distrusts_strangers" for t, _ in result)


def test_multiple_rules_fire() -> None:
    """Несколько правил могут сработать одновременно."""
    engine = MemoryPromotionEngine()
    traits = {"resentment": 0.4, "fear": 0.3, "suspicious": 0.4}
    result = engine.check_identity(traits)
    # distrusts_strangers + hostile_disposition
    assert len(result) == 2
    names = {t for t, _ in result}
    assert "distrusts_strangers" in names
    assert "hostile_disposition" in names


# ── MemoryManager.check_identity_promotion ──


def test_promotion_applies_to_cache() -> None:
    """check_identity_promotion записывает новые черты в identity_cache."""
    mm = _make_manager()
    # Предзаполняем кэш через apply_identity_weights
    mm.apply_identity_weights(
        "camp_1",
        "npc_01",
        [
            ("resentment", 0.35),
            ("fear", 0.25),
        ],
    )
    # Проверяем что черты записаны
    assert mm.get_identity_traits("camp_1", "npc_01")["resentment"] == 0.35

    # Запускаем проверку мета-паттернов
    new_traits = mm.check_identity_promotion("camp_1", "npc_01")
    assert len(new_traits) == 1
    assert new_traits[0][0] == "distrusts_strangers"

    # Новая черта должна быть в кэше
    final = mm.get_identity_traits("camp_1", "npc_01")
    assert "distrusts_strangers" in final
    assert final["distrusts_strangers"] > 0


def test_promotion_empty_when_no_rules() -> None:
    """Нет подходящих правил → пустой список, кэш не меняется."""
    mm = _make_manager()
    mm.apply_identity_weights("camp_1", "npc_01", [("resentment", 0.1)])
    new_traits = mm.check_identity_promotion("camp_1", "npc_01")
    assert new_traits == []
    assert "distrusts_strangers" not in mm.get_identity_traits("camp_1", "npc_01")

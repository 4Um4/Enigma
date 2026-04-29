"""Тесты механики раскрытия секретов (Этап 5).

cd backend; python -m pytest tests/test_discovery_mechanics.py -v 2>&1 | Select-Object -Last 20

Проверяет:
- discovery_check: разные типы давления дают разный результат
- assess_secrets_under_pressure: массовая проверка секретов
- Формула: физическое > угроза > запугивание > нудные вопросы

path: /backend/tests/test_discovery_mechanics.py
Назначение: Тесты для discovery_check и assess_secrets_under_pressure (Этап 5)
Зависимости: app.services.memory.memory_manager, app.models.npc_state
Основные сущности: test_discovery_check_basic, test_discovery_by_pressure_type, test_assess_secrets
"""
from app.models.npc_state import DiscoveryCrack, EventMemory, MemoryStage


def _make_secret(importance: float = 0.7, accessibility: float = 0.9) -> EventMemory:
    """Секретное воспоминание для тестов."""
    return EventMemory(
        event_type="witnessed_crime",
        target_id="player",
        emotion_tag="fearful",
        day=1,
        importance=importance,
        clarity=0.9,
        confidence=0.9,
        decay_rate=0.03,
        stage=MemoryStage.FRESH,
        summary="Видел как трактирщик прячет тело в подвале",
        npc_id="maid_lusya",
        tags=("witnessed_crime", "negative"),
        is_secret=True,
        known_by=("tavern_keeper",),
        hidden_from=("player",),
        accessibility=accessibility,
    )


def _make_manager():
    from app.services.memory.memory_manager import MemoryManager
    from unittest.mock import MagicMock
    mock_layered = MagicMock()
    return MemoryManager(layered_memory=mock_layered, data_dir="data")


# ── discovery_check: базовые сценарии ───────────────────────────────────


def test_no_pressure_no_crack() -> None:
    """Без давления секрет не трескается."""
    mm = _make_manager()
    secret = _make_secret(importance=0.7)
    result = mm.discovery_check(
        secret,
        pressure_type="question",
        pressure_count=1,
        npc_stress=0.0,
        npc_trust=0.0,
    )
    assert result == DiscoveryCrack.NONE


def test_physical_pressure_cracks_deep_secret() -> None:
    """Физическое давление может треснуть глубокий секрет."""
    mm = _make_manager()
    secret = _make_secret(importance=0.8)
    result = mm.discovery_check(
        secret,
        pressure_type="physical",
        pressure_count=3,
        npc_stress=0.9,
        npc_trust=-0.5,
    )
    # physical (0.45) × 1.2 = 0.54, resistance = 0.64, trust = +0.075, stress = +0.015
    # total = 0.64 + 0.075 - 0.54 - 0.015 = 0.16 → PARTIAL
    assert result == DiscoveryCrack.PARTIAL


def test_physical_beats_questions() -> None:
    """Физическое давление эффективнее 10 вопросов."""
    mm = _make_manager()
    secret = _make_secret(importance=0.6)

    result_phys = mm.discovery_check(
        secret,
        pressure_type="physical",
        pressure_count=1,
        npc_stress=0.5,
        npc_trust=0.0,
    )
    result_q = mm.discovery_check(
        secret,
        pressure_type="question",
        pressure_count=10,
        npc_stress=0.5,
        npc_trust=0.0,
    )
    # physical должен быть слабее NONE чем questions
    _order = [DiscoveryCrack.BROKEN, DiscoveryCrack.PARTIAL, DiscoveryCrack.CRACK, DiscoveryCrack.NONE]
    assert _order.index(result_phys) < _order.index(result_q)


def test_low_trust_adds_resistance() -> None:
    """Низкий trust = упрямство, секрет сложнее раскрыть."""
    mm = _make_manager()
    secret = _make_secret(importance=0.5)

    result_neutral = mm.discovery_check(
        secret, pressure_type="threat", pressure_count=1, npc_stress=0.5, npc_trust=0.0,
    )
    result_distrust = mm.discovery_check(
        secret, pressure_type="threat", pressure_count=1, npc_stress=0.5, npc_trust=-0.8,
    )
    _order = [DiscoveryCrack.BROKEN, DiscoveryCrack.PARTIAL, DiscoveryCrack.CRACK, DiscoveryCrack.NONE]
    assert _order.index(result_distrust) >= _order.index(result_neutral)


def test_high_stress_helps_but_not_auto() -> None:
    """Высокий стресс снижает сопротивление, но не раскрывает сам по себе."""
    mm = _make_manager()
    secret = _make_secret(importance=0.9)  # очень глубокий секрет

    # Стресс 0.95 + угроза — трескает даже глубокий секрет
    result = mm.discovery_check(
        secret, pressure_type="threat", pressure_count=1, npc_stress=0.95, npc_trust=0.0,
    )
    # resistance = 0.72, threat = 0.35, stress_help = 0.0225 → total = 0.347 → CRACK
    assert result == DiscoveryCrack.CRACK


def test_repeated_pressure_diminishing_returns() -> None:
    """Повторное давление даёт убывающий бонус."""
    mm = _make_manager()
    secret = _make_secret(importance=0.5)

    r1 = mm.discovery_check(secret, pressure_type="intimidation", pressure_count=1, npc_stress=0.3, npc_trust=0.0)
    r3 = mm.discovery_check(secret, pressure_type="intimidation", pressure_count=3, npc_stress=0.3, npc_trust=0.0)
    r10 = mm.discovery_check(secret, pressure_type="intimidation", pressure_count=10, npc_stress=0.3, npc_trust=0.0)

    _order = [DiscoveryCrack.BROKEN, DiscoveryCrack.PARTIAL, DiscoveryCrack.CRACK, DiscoveryCrack.NONE]
    # Каждое повторение должно быть слабее или равно предыдущему шагу прироста
    assert _order.index(r10) <= _order.index(r3) <= _order.index(r1)


# ── assess_secrets_under_pressure ────────────────────────────────────────


def test_assess_returns_only_cracked() -> None:
    """assess возвращает только треснувшие секреты, не NONE."""
    mm = _make_manager()
    deep = _make_secret(importance=0.9)
    shallow = _make_secret(importance=0.3)
    cache = (deep, shallow)

    # intimidation (0.20) не трескает 0.9 importance, но трескает 0.3
    result = mm.assess_secrets_under_pressure(
        cache,
        hidden_from_id="player",
        pressure_type="intimidation",
        pressure_count=1,
        npc_stress=0.5,
        npc_trust=0.0,
    )
    # deep: resistance=0.72, strength=0.20 → total=0.52 → NONE
    # shallow: resistance=0.24, strength=0.20 → total=0.04 → CRACK
    assert len(result) == 1
    secrets_in_result = [m for m, _ in result]
    assert shallow in secrets_in_result
    assert deep not in secrets_in_result


def test_assess_skips_non_secrets() -> None:
    """assess игнорирует несекретные воспоминания."""
    mm = _make_manager()
    normal = EventMemory(
        event_type="player_talks", target_id="player", emotion_tag="neutral",
        day=1, importance=0.5, npc_id="maid_lusya", summary="Обычный разговор",
    )
    cache = (normal,)
    result = mm.assess_secrets_under_pressure(
        cache, hidden_from_id="player", pressure_type="physical", pressure_count=5,
    )
    assert result == []


def test_assess_skips_wrong_hidden_from() -> None:
    """assess игнорирует секреты скрытые от другого NPC."""
    mm = _make_manager()
    secret_from_guard = EventMemory(
        event_type="theft", target_id="guard", emotion_tag="fearful",
        day=1, importance=0.5, npc_id="maid_lusya", summary="Видела кражу",
        is_secret=True, hidden_from=("guard",), accessibility=0.9,
    )
    cache = (secret_from_guard,)
    result = mm.assess_secrets_under_pressure(
        cache, hidden_from_id="player", pressure_type="physical", pressure_count=5,
    )
    assert result == []


def test_assess_returns_crack_level() -> None:
    """assess возвращает корректный уровень трещины для каждого секрета."""
    mm = _make_manager()
    s1 = _make_secret(importance=0.6)  # средний — partial (total ≈ -0.075)
    s2 = _make_secret(importance=0.05)  # микроскопический — broken (total ≈ -0.515)
    cache = (s1, s2)

    result = mm.assess_secrets_under_pressure(
        cache,
        hidden_from_id="player",
        pressure_type="physical",
        pressure_count=3,
        npc_stress=0.9,
        npc_trust=0.0,
    )
    _by_mem = {m: c for m, c in result}
    assert _by_mem[s1] == DiscoveryCrack.PARTIAL
    assert _by_mem[s2] == DiscoveryCrack.BROKEN
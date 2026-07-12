"""
Файл: backend/tests/sandbox/stress/test_schedule_override.py
Назначение: Стресс-песочница. Проверяет Cognitive Override Guard (ADR-052).
            Доказывает, что Attention Capture (recent_directive.interrupts_routine=True) блокирует
            выполнение расписания (work, move) в LifeEngine.
Зависимости: app.services.npc.life_engine
Основные сущности: TestScheduleOverride

Запуск: pytest backend/tests/sandbox/stress/test_schedule_override.py -s
"""

import pytest
from app.services.npc.life_engine import LifeEngine


@pytest.fixture
def engine() -> LifeEngine:
    """Инстанс LifeEngine без внешних IO зависимостей."""
    return LifeEngine()


@pytest.fixture
def suppressed_npc() -> dict:
    """NPC с захваченным вниманием (recent_directive.interrupts_routine=True). Имеет активное расписание."""
    return {
        "id": "worker_01",
        "perceptual_kernel": {
            "threat_gradient": 0.8,
            "recent_directive": {
                "source": "player",
                "salience": 0.85,
                "interrupts_routine": True,
            },  # Ключевое условие ADR-056
            "compliance_bias": 0.6,
        },
        "routine": {"current": "sleeping", "schedule": {"06:00-22:00": "working", "22:00-06:00": "sleeping"}},
        "activity_map": {
            "working": {"location": "forge", "position": "anvil", "display": "Кует металл"},
            "sleeping": {"location": "home", "position": "bed", "display": "Спит"},
        },
        "location": "home",
    }


@pytest.fixture
def free_npc() -> dict:
    """NPC со свободным вниманием (без recent_directive). Имеет активное расписание."""
    return {
        "id": "worker_02",
        "perceptual_kernel": {
            "threat_gradient": 0.1,
            "recent_directive": None,  # Нет захвата внимания
            "compliance_bias": 0.0,
        },
        "routine": {"current": "sleeping", "schedule": {"06:00-22:00": "working", "22:00-06:00": "sleeping"}},
        "activity_map": {
            "working": {"location": "forge", "position": "anvil", "display": "Кует металл"},
            "sleeping": {"location": "home", "position": "bed", "display": "Спит"},
        },
        "location": "home",
    }


def test_cognitive_override_guard_blocks_schedule(engine, suppressed_npc, free_npc):
    """
    СЦЕНАРИЙ: Сравниваем NPC с подавленной и свободной инициативой в рабочее время.
    ОЖИДАНИЕ: NPC с Attention Capture (salience=0.85) игнорирует расписание (замораживает бытовуху).
              Свободный NPC (без recent_directive) начинает работу.
    """
    # 10:00 — рабочее время по расписанию
    current_time = "10:00"

    # Вызов логики расписания (минорный цикл LifeEngine)
    changes_suppressed, _ = engine._simulate_minor(suppressed_npc, current_time=current_time, tick=1)
    changes_free, _ = engine._simulate_minor(free_npc, current_time=current_time, tick=1)

    # Аудит: Подавленный NPC не должен менять локацию (вернулся [], None)
    assert changes_suppressed == [], "Подавленный NPC не должен идти на работу (паралич воли)"

    # Аудит: Свободный NPC должен создать SceneChange для перехода на работу
    assert len(changes_free) > 0, "Свободный NPC должен начать работу по расписанию"

    print("\n--- SCHEDULE OVERRIDE TRACE ---")
    print(f"Worker 01 (suppressed=0.85): changes={changes_suppressed} (EXPECTED: [])")
    print(f"Worker 02 (suppressed=0.10): changes={len(changes_free)} items (EXPECTED: >0)")

"""
path: backend/tests/sandbox/fixture_loader.py
Назначение: WORLD SNAPSHOT (мандат S268, приказ Мастера) — консервированный
    детерминированный вход для causal-гейтов. Один механизм на все тесты:
    фиксирует world data + objects + NPC initial state + portions +
    initial positions + конфигурацию. RUN A == RUN B означает одно и то же
    начальное состояние. Живой мир — запрещён для causal acceptance
    (A(world_t) vs B(world_t+Δ) — два разных эксперимента).
Зависимости: os, pathlib (без app-импортов — загрузчик до settings).
Основные сущности: FIXTURE_DIR, fixture_env(), has_fixture()

Запуск: python -m py_compile backend/app/services/tick_utils.py backend/tests/sandbox/fixture_loader.py
"""
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "campaign_open_road"


def has_fixture() -> bool:
    """Фикстура консервирована и полна (sessions/world_tick присутствуют)."""
    return FIXTURE_DIR.exists() and (FIXTURE_DIR / "sessions").exists()


def consume_fixture(settings) -> None:
    """Подключает фикстуру как data_dir с ЧИСТОЙ гарантией:
    runtime-хвосты (logs, world_tick.json) тест-прогона не мутируют
    консервант (урок S268: logs/*.jsonl и world_tick ползли в
    фикстуру). Вызывать ДО импорта сервисов."""
    settings.data_dir = str(FIXTURE_DIR)
    _wt = FIXTURE_DIR / "sessions" / "Open_road" / "world_tick.json"
    if _wt.exists():
        _wt.unlink()


def fixture_env() -> dict:
    """Env-инъекция для subprocess-раннеров (прецедент iron_river:
    в -c контексте __file__ не существует — только env-канал)."""
    return {"ENIGMA_FIXTURE_DIR": str(FIXTURE_DIR)} if has_fixture() else {}
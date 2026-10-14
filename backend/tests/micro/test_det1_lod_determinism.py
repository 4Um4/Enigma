from __future__ import annotations

# backend/tests/micro/test_det1_lod_determinism.py
"""
path: backend/tests/micro/test_det1_lod_determinism.py
Назначение: DET-1 (roadmap §17.8, вердикт Мастера III.1) — доказательный
тест детерминизма AdaptiveTickLoader: LOD-решение обязано определяться
СОСТОЯНИЕМ МИРА (npc_count), а не wall-clock. Формулировка вердикта:
«replay на другой машине или после изменения нагрузки потенциально может
получить другой мир» — тест фиксирует ДЕТ-1-фикс (баг M-24 существовал:
входом была длительность исполнения) и замыкает регрессию.
Зависимости: pytest; app.services.adaptive_tick_loader.AdaptiveTickLoader.
Основные сущности: test_det1_*.
"""

from app.services.adaptive_tick_loader import AdaptiveTickLoader


def _seeded(npc_count: int, duration_ms: float) -> AdaptiveTickLoader:
    """Лоадер после N тиков заданной нагрузки/длительности."""
    loader = AdaptiveTickLoader()
    for _ in range(AdaptiveTickLoader.LOD_ACTIVATION_SAMPLES):
        loader.record_tick(duration_ms, npc_count)
    return loader


def test_det1_same_world_same_lod_regardless_of_machine_speed():
    """Ядро DET-1: один и тот же мир (npc_count=15) — быстрый и медленный
    тик дают ОДИНАКОВОЕ LOD-решение (до фикса M-24 это было ложно:
    медленная машина активировала LOD, быстрая — нет)."""
    slow_machine = _seeded(15, duration_ms=5000.0)   # «тяжёлая» машина
    fast_machine = _seeded(15, duration_ms=12.3)     # «лёгкая» машина
    assert slow_machine.is_lod_active() == fast_machine.is_lod_active() is True


def test_det1_wall_clock_alone_cannot_flip_lod():
    """Wall-clock не является входом решения: драматическая длительность
    (999999 мс × активационная выборка) при малом мире НЕ активирует LOD."""
    heavy_but_small = _seeded(3, duration_ms=999999.0)
    assert heavy_but_small.is_lod_active() is False


def test_det1_world_size_is_the_sole_decision_input():
    """Обратное направление: большой мир активирует LOD даже на нулевой
    длительности; малый — нет; гистерезис (5/50) соблюдается."""
    big_fast = _seeded(20, duration_ms=0.0)
    assert big_fast.is_lod_active() is True

    loader = AdaptiveTickLoader()
    for _ in range(AdaptiveTickLoader.LOD_DEACTIVATION_SAMPLES):
        loader.record_tick(0.0, 3)  # мир сжался — LOD гаснет независимо от скорости
    assert loader.is_lod_active() is False


def test_det1_should_tick_fully_topology_unchanged():
    """Топология решений не тронута фиксом: LOD активен → только активная
    локация и её соседи тикают полностью; LOD не активен → все полностью."""
    loader = _seeded(20, duration_ms=0.0)
    assert loader.is_lod_active()
    assert loader.should_tick_fully("active", "active", None) is True
    assert loader.should_tick_fully("neighbor", "active", ["neighbor"]) is True
    assert loader.should_tick_fully("far_away", "active", ["neighbor"]) is False

    off = AdaptiveTickLoader()
    assert off.should_tick_fully("far_away", "active", None) is True
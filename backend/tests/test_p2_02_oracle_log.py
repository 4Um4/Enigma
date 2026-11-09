# path: backend/tests/test_p2_02_oracle_log.py
# Назначение: P2-02 (ADR-O-439 D.2) — unit-тесты структурного лога оракула
#     локации. Единый helper log_oracle_decision для 3 оракулов (HTTP/IDLE/BRIDGE):
#     world_xy, candidates, winner, prev→new, правило. Без поведенческих
#     изменений — только диагностика рассинхрона «логика/визуал» (C-P1).
# Зависимости: pytest, logging capture, oracle_log.log_oracle_decision.
# Основные сущности:
#     - test_log_info_on_location_change — смена локации → INFO + LOCATION_CHANGED
#     - test_log_debug_on_no_change — нет смены → DEBUG + no_change
#     - test_log_warning_when_outside — winner=None → WARNING + OUTSIDE_ALL_CHUNKS
#     - test_log_structure_contains_all_fields — структура: tag/world/candidates/winner/prev/new/rule
#     - test_prefix_spatial_oracle_preserved — [SPATIAL_ORACLE] префикс (test_tz3/bm_cell_a_repeat)
#     - test_3_call_sites_use_helper — source-инспекция: routes/game_loop/bridge вызывают helper
"""
P2-02 (ADR-O-439 D.2): наблюдаемость оракула локации.

Контракт ROADMAP §P2-02:
- Структурный лог (одна строка): world_xy, кандидаты, выбранная локация, правило.
- При смене локации относительно metadata — INFO-лог.
- Без PII в логах.

Реализован как единый helper log_oracle_decision в backend/app/services/spatial/oracle_log.py.
Вызывается из 3 оракулов:
- routes.py (HTTP path) — tag="HTTP"
- game_loop.py (idle oracle) — tag="IDLE"
- game_loop_bridge.py (frontend oracle) — tag="BRIDGE"

Multi-chunk warning остаётся в SpatialRegistry.resolve_primary (P2-01) — не дублируется.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.services.spatial.oracle_log import log_oracle_decision


# ─────────────────────────────────────────────────────────────────────────────
# Фикстура: capture log records
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def capture_logs(caplog):
    """Capture log records at DEBUG level for oracle_log logger."""
    caplog.set_level(logging.DEBUG, logger="app.services.spatial.oracle_log")
    return caplog


# ─────────────────────────────────────────────────────────────────────────────
# Тест 1: смена локации → INFO + LOCATION_CHANGED
# ─────────────────────────────────────────────────────────────────────────────


def test_log_info_on_location_change(capture_logs) -> None:
    """P2-02: смена локации (prev != new, winner not None) → INFO + LOCATION_CHANGED."""
    log_oracle_decision(
        tag="HTTP",
        world_x=33.0,
        world_y=12.0,
        candidates_count=1,
        winner_id="tavern",
        prev_location="city_gate",
        new_location="tavern",
        source="routes.py:1029",
    )
    # Найти запись уровня INFO
    info_records = [r for r in capture_logs.records if r.levelno == logging.INFO]
    assert len(info_records) == 1, f"expected 1 INFO, got {len(info_records)}"
    msg = info_records[0].getMessage()
    assert "LOCATION_CHANGED" in msg, f"msg={msg!r}"
    assert "tag=HTTP" in msg
    assert "winner=tavern" in msg
    assert "prev=city_gate" in msg
    assert "new=tavern" in msg


# ─────────────────────────────────────────────────────────────────────────────
# Тест 2: нет смены → DEBUG + no_change
# ─────────────────────────────────────────────────────────────────────────────


def test_log_debug_on_no_change(capture_logs) -> None:
    """P2-02: нет смены (prev == new, winner not None) → DEBUG + no_change."""
    log_oracle_decision(
        tag="IDLE",
        world_x=33.0,
        world_y=12.0,
        candidates_count=1,
        winner_id="tavern",
        prev_location="tavern",
        new_location="tavern",
        source="game_loop.py:1317",
    )
    debug_records = [r for r in capture_logs.records if r.levelno == logging.DEBUG]
    assert len(debug_records) == 1, f"expected 1 DEBUG, got {len(debug_records)}"
    msg = debug_records[0].getMessage()
    assert "no_change" in msg, f"msg={msg!r}"
    assert "tag=IDLE" in msg


# ─────────────────────────────────────────────────────────────────────────────
# Тест 3: winner=None → WARNING + OUTSIDE_ALL_CHUNKS
# ─────────────────────────────────────────────────────────────────────────────


def test_log_warning_when_outside(capture_logs) -> None:
    """P2-02: winner=None (точка вне footprint'ов) → WARNING + OUTSIDE_ALL_CHUNKS."""
    log_oracle_decision(
        tag="BRIDGE",
        world_x=1000.0,
        world_y=1000.0,
        candidates_count=0,
        winner_id=None,
        prev_location="tavern",
        new_location="tavern",  # fallback к saved
        source="game_loop_bridge.py:171",
    )
    warn_records = [r for r in capture_logs.records if r.levelno == logging.WARNING]
    assert len(warn_records) == 1, f"expected 1 WARNING, got {len(warn_records)}"
    msg = warn_records[0].getMessage()
    assert "OUTSIDE_ALL_CHUNKS" in msg, f"msg={msg!r}"
    assert "winner=None" in msg
    assert "candidates=0" in msg


# ─────────────────────────────────────────────────────────────────────────────
# Тест 4: структура содержит все поля (D.2 контракт)
# ─────────────────────────────────────────────────────────────────────────────


def test_log_structure_contains_all_fields(capture_logs) -> None:
    """P2-02: структурный лог содержит все поля контракта D.2.

    Контракт: world_xy, candidates, winner, prev→new, rule.
    """
    log_oracle_decision(
        tag="HTTP",
        world_x=33.5,
        world_y=12.7,
        candidates_count=2,
        winner_id="tavern",
        prev_location="city_gate",
        new_location="tavern",
        source="routes.py:1029",
    )
    # INFO запись (смена)
    info_records = [r for r in capture_logs.records if r.levelno == logging.INFO]
    assert len(info_records) == 1
    msg = info_records[0].getMessage()

    # Все поля контракта D.2
    assert "[SPATIAL_ORACLE]" in msg, "префикс сохранён"
    assert "tag=HTTP" in msg, "tag источника"
    assert "world=(33.5, 12.7)" in msg, "world_xy координаты"
    assert "candidates=2" in msg, "количество кандидатов"
    assert "winner=tavern" in msg, "победитель"
    assert "prev=city_gate" in msg, "предыдущая локация"
    assert "new=tavern" in msg, "новая локация"
    assert "rule=D.2" in msg, "правило выбора"
    assert "src=routes.py:1029" in msg, "source для диагностики"


# ─────────────────────────────────────────────────────────────────────────────
# Тест 5: [SPATIAL_ORACLE] префикс сохранён (контракт test_tz3/bm_cell_a_repeat)
# ─────────────────────────────────────────────────────────────────────────────


def test_prefix_spatial_oracle_preserved(capture_logs) -> None:
    """P2-02: [SPATIAL_ORACLE] префикс сохранён для обратной совместимости.

    test_tz3_contract_repair.py:118 — assert "SPATIAL_ORACLE" in source.
    bm_cell_a_repeat.py:365 — фильтр логов по "[SPATIAL_ORACLE".
    Префикс НЕ должен ломаться.
    """
    log_oracle_decision(
        tag="HTTP",
        world_x=33.0,
        world_y=12.0,
        candidates_count=1,
        winner_id="tavern",
        prev_location="tavern",
        new_location="tavern",
    )
    # Любая запись (DEBUG в этом случае)
    assert len(capture_logs.records) >= 1
    msg = capture_logs.records[0].getMessage()
    assert "[SPATIAL_ORACLE]" in msg, f"префикс нарушен: {msg!r}"


# ─────────────────────────────────────────────────────────────────────────────
# Тест 6: 3 call-site'а используют helper (source-инспекция)
# ─────────────────────────────────────────────────────────────────────────────


def test_3_call_sites_use_helper() -> None:
    """P2-02: 3 оракула вызывают log_oracle_decision (source-инспекция).

    Без запуска сервера — проверяем, что source-код содержит вызов helper'а
    в каждом из 3 мест. Это гарантирует, что P2-02 не деградирует до
    «забыли подключить в одном из оракулов».
    """
    backend_root = Path(__file__).resolve().parents[2]
    frontend_root = backend_root / "frontend"

    files_to_check = [
        (backend_root / "backend" / "app" / "api" / "routes.py", "log_oracle_decision", "HTTP"),
        (backend_root / "backend" / "app" / "services" / "game_loop" / "game_loop.py", "log_oracle_decision", "IDLE"),
        (frontend_root / "game_loop_bridge.py", "log_oracle_decision", "BRIDGE"),
    ]

    for file_path, helper_name, expected_tag in files_to_check:
        assert file_path.exists(), f"файл не найден: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        assert helper_name in content, (
            f"{file_path.name}: helper {helper_name} не вызывается"
        )
        # Проверяем, что tag соответствует ожидаемому
        # (HTTP/IDLE/BRIDGE — каждый оракул использует свой tag)
        assert f'tag="{expected_tag}"' in content, (
            f"{file_path.name}: tag={expected_tag!r} не найден"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Тест 7: helper доступен из frontend через importlib (как SpatialRegistry)
# ─────────────────────────────────────────────────────────────────────────────


def test_helper_importable_via_importlib() -> None:
    """P2-02: frontend game_loop_bridge.py импортирует helper через importlib.

    Паритет с SpatialRegistry (game_loop_bridge.py:158) — frontend использует
    importlib для backend-модулей. Проверяем, что путь
    'app.services.spatial.oracle_log' импортируется.
    """
    import importlib

    module = importlib.import_module("app.services.spatial.oracle_log")
    assert hasattr(module, "log_oracle_decision")
    assert callable(module.log_oracle_decision)
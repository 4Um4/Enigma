"""Замок DEBT-FE-DELTAS (Rule 11 / Устав §6.3, §10.3-№18).

Канал: pipeline_runner.ctx.significant_events (= TickMutation.npc_deltas,
List[StateDeltas]) → TickResultDTO → game_loop.idle_tick return "events" →
HTTP idle_tick → FE телеграф.

Контракт после ADR-O-420 (LC-IMPL-1; эволюция замка — канон сменился
по каталогу LC 2026-10-05, тихая эволюция замков запрещена):
- game_loop.idle_tick по-прежнему НЕ проектирует significant_events
  (сырые StateDeltas / ментальные поля — Rule 11, бессрочно);
- "events" = наблюдаемая проекция {cause,target,value} только уже
  произошедшего (ADR-O-420), сборка за флагом IDLE_EVENTS_PROJECTION_ENABLED;
  OFF = [] (no-op);
- routes.idle_tick читает ключ "events" (выровнен с return game_loop);
  легаси-чтение "significant_events" у dict всегда давало None.

Ядро (TickResultDTO.significant_events → world_projection_buffer /
commit_phase / time_skip_executor) не тронуто — internal-потребители
легитимны (Rule 11 регулирует только фронт-границу).
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
GAME_LOOP = ROOT / "backend/app/services/game_loop/game_loop.py"
ROUTES = ROOT / "backend/app/api/routes.py"


def _read(path: Path) -> str:
    # utf-8-sig: урок BOM ×11 — чтение обязано переживать BOM
    return path.read_text(encoding="utf-8-sig")


def _idle_tick_body() -> str:
    src = _read(GAME_LOOP)
    start = src.index("def idle_tick(")
    end = src.index("async def run_turn(")
    return src[start:end]


def test_idle_tick_does_not_project_state_deltas() -> None:
    """Греп-страж: StateDeltas не во фронт-канале (бессрочно); проекция —
    за флагом ADR-O-420 (эволюция замка K2, канон сменился)."""
    body = _idle_tick_body()
    assert "significant_events" not in body, (
        "DEBT-FE-DELTAS регрессия: idle_tick снова проектирует "
        "significant_events (сырые StateDeltas) во фронт-канал (Rule 11)"
    )
    assert '"events": _idle_events' in body, (
        "ADR-O-420: ожидается наблюдаемая проекция "
        '"events": _idle_events в return idle_tick'
    )
    assert "idle_event_projection" in body, (
        "ADR-O-420: wiring проекции исчез из idle_tick (тихая регрессия)"
    )


def test_routes_reads_aligned_events_key() -> None:
    """routes.idle_tick читает ключ 'events' (dict-ветка); чтение
    'significant_events' у dict всегда давало None — мёртвый канал."""
    src = _read(ROUTES)
    assert '_result.get("significant_events")' not in src
    assert '_result.get("events")' in src


def test_routes_idle_tick_passthrough_events() -> None:
    """Runtime: routes пробрасывает выровненный ключ как есть
    (рассинхрон 'significant_events'-у-dict не возрождается)."""
    from app.api.routes import idle_tick as endpoint

    class _StubLoop:
        def idle_tick(self, campaign_id: str) -> dict:
            return {
                "status": "ok",
                "events": [],
                "world_snapshot": None,
                "npc_positions": {},
            }

    resp = endpoint("c1", game_loop=_StubLoop())
    assert resp["events"] == []


def test_projection_flag_off_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-O-420 runtime-замок: OFF = канал пуст (полная байт-чистота
    Control дополнительно доказывается SUPERBOX lc_gc01_world_speaks_test)."""
    from app.services.game_loop import idle_event_projection as iep

    monkeypatch.setenv("IDLE_EVENTS_PROJECTION_ENABLED", "0")
    assert iep.idle_events_projection_enabled() is False
    assert iep.project_idle_events([], {}) == []
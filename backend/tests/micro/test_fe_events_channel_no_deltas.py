"""Замок DEBT-FE-DELTAS (Rule 11 / Устав §6.3, §10.3-№18).

Канал: pipeline_runner.ctx.significant_events (= TickMutation.npc_deltas,
List[StateDeltas]) → TickResultDTO → game_loop.idle_tick return "events" →
HTTP idle_tick → FE телеграф.

Контракт после закрытия долга:
- game_loop.idle_tick НЕ проектирует significant_events во фронт-канал
  (return содержит "events": [] — канал спаркован; возрождение = честная
  наблюдаемая проекция, решение гейм-дизайна).
- routes.idle_tick читает ключ "events" (выровнен с return game_loop);
  легаси-чтение "significant_events" у dict всегда давало None.

Ядро (TickResultDTO.significant_events → world_projection_buffer /
commit_phase / time_skip_executor) не тронуто — internal-потребители
легитимны (Rule 11 регулирует только фронт-границу).
"""

from __future__ import annotations

from pathlib import Path

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
    """Греп-страж: return idle_tick не несёт StateDeltas во фронт-канал."""
    body = _idle_tick_body()
    assert "significant_events" not in body, (
        "DEBT-FE-DELTAS регрессия: idle_tick снова проектирует "
        "significant_events (сырые StateDeltas) во фронт-канал (Rule 11)"
    )
    assert '"events": []' in body, (
        "Контракт канала изменён без замка: ожидается спарк "
        '"events": [] в return idle_tick (возрождение = проекция, '
        "решение гейм-дизайна, не молчаливая утечка)"
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
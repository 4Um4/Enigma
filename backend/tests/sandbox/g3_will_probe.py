# path: /project/backend/tests/sandbox/g3_will_probe.py
# Назначение: G3 Этап 2 (ADR-O-410) — приёмка ЖИВОЙ ВОЛИ: агент сам
#     выбирает объектную цель. Без инжекта windup: спавн стула → живые
#     тики → воля (resolver→Opportunity→DecisionHub→STEAL(wo_*)) →
#     windup → TAKE → HELD_BY-мутация → THEFT. A/B OFF/ON: OFF —
#     steal-канал деградирует в OBSERVE (BUG-01), мутации нет.
#     GC-00-стандарт; INVALID RUN-guard.
# Зависимости: tests.gameplay.harness, app.services.world
# Основные сущности: _rail, main
# Запуск: cd backend; python -m tests.sandbox.g3_will_probe; cd ..
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_ROOT / "backend"))

from tests.gameplay.harness import TavernGameplayHarness  # noqa: E402

_CAMPAIGN = "Open_road"
_LOCATION = "tavern_silver_wolf"
_ACTOR = "thief_shadow"
_CHAIR_ID = "wo_g3_will_chair"
_TICKS = 80


def _holder_of(scene: Dict[str, Any]) -> Any:
    _raw = (scene.get("world_objects") or {}).get(_CHAIR_ID)
    return (_raw or {}).get("holder") if isinstance(_raw, dict) else None


def _chair_exists(scene: Dict[str, Any]) -> bool:
    return bool((scene.get("world_objects") or {}).get(_CHAIR_ID))


def _rail(flag: str) -> Dict[str, Any]:
    import os

    os.environ["W3_G3_ENABLED"] = flag
    _theft: List[str] = []
    _report: Dict[str, Any] = {"rail": flag}
    try:
        with TavernGameplayHarness() as _h:
            from app.services.events.event_bus import get_event_bus
            from app.services.events.event_types import EventType

            def _on_theft(event: Any) -> None:
                _p = getattr(event, "payload", {}) or {}
                if getattr(event, "source", "") == _ACTOR and _p.get(
                    "target_id", ""
                ) == _CHAIR_ID:
                    _theft.append(_CHAIR_ID)

            get_event_bus().subscribe(EventType.THEFT, _on_theft)
            _h.advance_ticks(1)  # прогрев сцены (урок P11)
            _report["spawned"] = _h.spawn_world_object(
                _CHAIR_ID, "chair", (8.2, 12.8)
            )
            # Реальное давление (production-путь run_turn): угрозы игрока
            # могут перевести волю вора в deceptive/broken → R6.3-unlock
            # STEAL. Не инжект — живой контур (противоположность
            # Goran-β, который инъецировал входы).
            for _ in range(3):
                try:
                    _h.player_action("угрожаю thief_shadow")
                except Exception as _pe:  # noqa: S110
                    print(f"[G3-WILL] pressure fault: {_pe}")
            _h.advance_ticks(_TICKS)  # живая воля, БЕЗ инжекта
            _scene = _h.get_scene_fresh() or _h.get_scene() or {}
            _report["holder_after"] = _holder_of(_scene)
            _report["theft_events"] = len(_theft)
            _report["chair_exists"] = _chair_exists(_scene)
    finally:
        os.environ.pop("W3_G3_ENABLED", None)
    return _report


def main() -> int:
    # VIII.5: раскрыть INFO-слой (DECISION_HUB/G3_TGT) — без этого
    # диагностика воли слепа (в выводе харнесса только WARNING+).
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s"
    )
    _off = _rail("0")
    _on = _rail("1")
    for _r in (_off, _on):
        if not _r.get("spawned") or not _r.get("chair_exists"):
            print(f"[G3-WILL] INVALID RUN: {_r}")
            return 1
    print(f"[G3-WILL] OFF: {_off}")
    print(f"[G3-WILL] ON:  {_on}")
    # OFF: канал воли закрыт → holder None. ON: воля жива → holder = вор.
    _ok_off = _off["holder_after"] is None
    _ok_on = _on["holder_after"] == _ACTOR and _on["theft_events"] >= 1
    print(f"[G3-WILL] verdict: {'GREEN' if (_ok_off and _ok_on) else 'RED'}")
    return 0 if (_ok_off and _ok_on) else 1


if __name__ == "__main__":
    raise SystemExit(main())